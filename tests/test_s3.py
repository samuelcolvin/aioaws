import asyncio
import secrets
from datetime import datetime, timezone

import pytest
from foxglove.test_server import DummyServer
from httpx import AsyncClient
from pytest_toolbox.comparison import CloseToNow

from aioaws.core import RequestError
from aioaws.s3 import S3Client, S3Config, S3File, to_key

from .conftest import AWS

pytestmark = pytest.mark.asyncio

run_prefix = secrets.token_hex()[:10]


def test_upload_url():
    s3 = S3Client('-', S3Config('testing', 'testing', 'testing', 'testing.com'))
    d = s3.signed_upload_url(
        path='testing/', filename='test.png', content_type='image/png', size=123, expires=datetime(2032, 1, 1)
    )
    assert d == {
        'url': 'https://testing.com/',
        'fields': {
            'Key': 'testing/test.png',
            'Content-Type': 'image/png',
            'AWSAccessKeyId': 'testing',
            'Content-Disposition': 'attachment; filename="test.png"',
            'Policy': (
                'eyJleHBpcmF0aW9uIjogIjIwMzItMDEtMDFUMDA6MDA6MDBaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiAidGVzdGluZy5jb'
                '20ifSwgeyJrZXkiOiAidGVzdGluZy90ZXN0LnBuZyJ9LCB7ImNvbnRlbnQtdHlwZSI6ICJpbWFnZS9wbmcifSwgWyJjb250ZW50LW'
                'xlbmd0aC1yYW5nZSIsIDEyMywgMTIzXSwgeyJDb250ZW50LURpc3Bvc2l0aW9uIjogImF0dGFjaG1lbnQ7IGZpbGVuYW1lPVwidGV'
                'zdC5wbmdcIiJ9XX0='
            ),
            'Signature': 'dnnmIX/z9J5ClnI11ZzDyPVSxUY=',
        },
    }


def test_upload_url_no_content_disp():
    s3 = S3Client('-', S3Config('testing', 'testing', 'testing', 'testing'))
    d = s3.signed_upload_url(
        path='testing/',
        filename='test.png',
        content_type='image/png',
        size=123,
        content_disp=False,
        expires=datetime(2032, 1, 1),
    )
    assert d == {
        'url': 'https://testing.s3.amazonaws.com/',
        'fields': {
            'Key': 'testing/test.png',
            'Content-Type': 'image/png',
            'AWSAccessKeyId': 'testing',
            'Policy': (
                'eyJleHBpcmF0aW9uIjogIjIwMzItMDEtMDFUMDA6MDA6MDBaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiAidGVzdGluZyJ9L'
                'CB7ImtleSI6ICJ0ZXN0aW5nL3Rlc3QucG5nIn0sIHsiY29udGVudC10eXBlIjogImltYWdlL3BuZyJ9LCBbImNvbnRlbnQtbGVuZ3'
                'RoLXJhbmdlIiwgMTIzLCAxMjNdXX0='
            ),
            'Signature': 'xi9Vv7t8UL2iaHtX88J/ezS+fBI=',
        },
    }


async def test_list(client: AsyncClient):
    s3 = S3Client(client, S3Config('testing', 'testing', 'testing', 'testing'))
    files = [f async for f in s3.list()]
    assert len(files) == 3
    assert files[0].dict() == dict(
        key='/foo.html',
        last_modified=datetime(2032, 1, 1, 12, 34, 56, tzinfo=timezone.utc),
        size=123,
        e_tag='aaa',
        storage_class='STANDARD',
    )


async def test_list_delete_many(client: AsyncClient, aws: DummyServer):
    s3 = S3Client(client, S3Config('testing', 'testing', 'testing', 'testing'))
    files = [f async for f in s3.list('many')]
    assert len(files) == 1500
    deleted_files = await s3.delete_recursive('many')
    assert len(deleted_files) == 1500
    assert aws.log == [
        'GET /s3/?list-type=2&prefix=many > 200',
        'GET /s3/?continuation-token=foobar123&list-type=2&prefix=many > 200',
        'GET /s3/?list-type=2&prefix=many > 200',
        'GET /s3/?continuation-token=foobar123&list-type=2&prefix=many > 200',
        'POST /s3/?delete=1 > 200',
        'POST /s3/?delete=1 > 200',
    ]


async def test_list_bad(client: AsyncClient):
    s3 = S3Client(client, S3Config('testing', 'testing', 'testing', 'testing'))
    with pytest.raises(RuntimeError, match='unexpected response from S3'):
        async for _ in s3.list('broken'):
            pass


def test_to_key():
    assert to_key('foobar') == 'foobar'
    assert to_key(S3File.construct(key='spam')) == 'spam'
    with pytest.raises(TypeError, match='must be a string or S3File object'):
        to_key(123)


async def test_real_upload(real_aws: AWS):
    async with AsyncClient(timeout=30) as client:
        s3 = S3Client(client, S3Config(real_aws.access_key, real_aws.secret_key, 'us-east-1', 'aioaws-testing'))

        path = f'{run_prefix}/testing/test.txt'
        await s3.upload(path, b'this is a test')

        try:
            files = [f.dict() async for f in s3.list(f'{run_prefix}/')]
            # debug(files)
            assert len(files) == 1
            assert files[0] == {
                'key': path,
                'last_modified': CloseToNow(delta=10),
                'size': 14,
                'e_tag': '54b0c58c7ce9f2a8b551351102ee0938',
                'storage_class': 'STANDARD',
            }
        finally:
            assert await s3.delete(path) == [path]
            assert [f.dict() async for f in s3.list(f'{run_prefix}/')] == []


async def test_real_download_link(real_aws: AWS):
    async with AsyncClient(timeout=30) as client:
        s3 = S3Client(client, S3Config(real_aws.access_key, real_aws.secret_key, 'us-east-1', 'aioaws-testing'))

        await s3.upload(f'{run_prefix}/foobar.txt', b'hello', content_type='text/html')

        try:
            url = s3.signed_download_url(f'{run_prefix}/foobar.txt')
            r = await client.get(url)
            assert r.status_code == 200, r.text
            assert r.text == 'hello'
            assert r.headers['content-type'] == 'text/html'

        finally:
            await s3.delete(f'{run_prefix}/foobar.txt')


async def test_real_many(real_aws: AWS):
    async with AsyncClient(timeout=30) as client:
        s3 = S3Client(client, S3Config(real_aws.access_key, real_aws.secret_key, 'us-east-1', 'aioaws-testing'))

        # upload many files
        await asyncio.gather(*[s3.upload(f'{run_prefix}/f_{i}.txt', f'file {i}'.encode()) for i in range(51)])

        deleted_files = await s3.delete_recursive(f'{run_prefix}/')
        assert len(deleted_files) == 51


async def test_bad_auth():
    async with AsyncClient(timeout=30) as client:
        s3 = S3Client(client, S3Config('BAD_access_key', 'BAD_secret_key', 'us-east-1', 'foobar'))

        with pytest.raises(RequestError) as exc_info:
            await s3.upload('foobar.txt', b'hello')

        assert exc_info.value.args[0] == 'unexpected response from POST "https://foobar.s3.amazonaws.com/": 403'
        assert str(exc_info.value).startswith(exc_info.value.args[0] + ', response:\n<?xml ')

        with pytest.raises(RequestError, match=r'POST "https://foobar.s3.amazonaws.com\?delete=1"'):
            await s3.delete('foobar.txt')
