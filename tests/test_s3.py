import asyncio
import secrets
from datetime import datetime, timezone

import pytest
from dirty_equals import IsNow, IsStr
from foxglove.test_server import DummyServer
from httpx import AsyncClient

from aioaws.core import RequestError
from aioaws.s3 import S3Client, S3Config, S3File, to_key

from .conftest import AWS

run_prefix = secrets.token_hex()[:10]


def test_upload_url_after_overriding_aws_client_endpoint(mocker):
    mocker.patch('aioaws.s3.utcnow', return_value=datetime(2032, 1, 1))
    s3 = S3Client('-', S3Config('testing', 'testing', 'testing', 'testing.com'))
    s3._aws_client.host = 'localhost:4766'
    s3._aws_client.schema = 'http'
    d = s3.signed_upload_url(
        path='testing/', filename='test.png', content_type='image/png', size=123, expires=datetime(2032, 1, 1)
    )
    assert d == {
        'url': 'http://localhost:4766/',
        'fields': {
            'Key': 'testing/test.png',
            'Content-Type': 'image/png',
            'Content-Disposition': 'attachment; filename="test.png"',
            'Policy': (
                'eyJleHBpcmF0aW9uIjogIjIwMzItMDEtMDFUMDA6MDA6MDBaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiAidGVzdGluZy5jb'
                '20ifSwgeyJrZXkiOiAidGVzdGluZy90ZXN0LnBuZyJ9LCB7ImNvbnRlbnQtdHlwZSI6ICJpbWFnZS9wbmcifSwgWyJjb250ZW50LW'
                'xlbmd0aC1yYW5nZSIsIDEyMywgMTIzXSwgeyJDb250ZW50LURpc3Bvc2l0aW9uIjogImF0dGFjaG1lbnQ7IGZpbGVuYW1lPVwidGV'
                'zdC5wbmdcIiJ9LCB7IngtYW16LWNyZWRlbnRpYWwiOiAidGVzdGluZy8yMDMyMDEwMS90ZXN0aW5nL3MzL2F3czRfcmVxdWVzdCJ9'
                'LCB7IngtYW16LWFsZ29yaXRobSI6ICJBV1M0LUhNQUMtU0hBMjU2In0sIHsieC1hbXotZGF0ZSI6ICIyMDMyMDEwMVQwMDAwMDBaI'
                'n1dfQ=='
            ),
            'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
            'X-Amz-Credential': 'testing/20320101/testing/s3/aws4_request',
            'X-Amz-Date': '20320101T000000Z',
            'X-Amz-Signature': '6f03af4c50aacb313ceb038743ca035bc2da2dc3bf9d1289f5cb946c6c940a60',
        },
    }


def test_upload_url(mocker):
    mocker.patch('aioaws.s3.utcnow', return_value=datetime(2032, 1, 1))
    s3 = S3Client('-', S3Config('testing', 'testing', 'testing', 'testing.com'))
    d = s3.signed_upload_url(
        path='testing/', filename='test.png', content_type='image/png', size=123, expires=datetime(2032, 1, 1)
    )
    assert d == {
        'url': 'https://testing.com/',
        'fields': {
            'Key': 'testing/test.png',
            'Content-Type': 'image/png',
            'Content-Disposition': 'attachment; filename="test.png"',
            'Policy': (
                'eyJleHBpcmF0aW9uIjogIjIwMzItMDEtMDFUMDA6MDA6MDBaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiAidGVzdGluZy5jb'
                '20ifSwgeyJrZXkiOiAidGVzdGluZy90ZXN0LnBuZyJ9LCB7ImNvbnRlbnQtdHlwZSI6ICJpbWFnZS9wbmcifSwgWyJjb250ZW50LW'
                'xlbmd0aC1yYW5nZSIsIDEyMywgMTIzXSwgeyJDb250ZW50LURpc3Bvc2l0aW9uIjogImF0dGFjaG1lbnQ7IGZpbGVuYW1lPVwidGV'
                'zdC5wbmdcIiJ9LCB7IngtYW16LWNyZWRlbnRpYWwiOiAidGVzdGluZy8yMDMyMDEwMS90ZXN0aW5nL3MzL2F3czRfcmVxdWVzdCJ9'
                'LCB7IngtYW16LWFsZ29yaXRobSI6ICJBV1M0LUhNQUMtU0hBMjU2In0sIHsieC1hbXotZGF0ZSI6ICIyMDMyMDEwMVQwMDAwMDBaI'
                'n1dfQ=='
            ),
            'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
            'X-Amz-Credential': 'testing/20320101/testing/s3/aws4_request',
            'X-Amz-Date': '20320101T000000Z',
            'X-Amz-Signature': '6f03af4c50aacb313ceb038743ca035bc2da2dc3bf9d1289f5cb946c6c940a60',
        },
    }


def test_upload_url_no_content_disp(mocker):
    mocker.patch('aioaws.s3.utcnow', return_value=datetime(2032, 1, 1))
    s3 = S3Client('-', S3Config('testing-access-key', 'testing-secret-key', 'testing-region', 'testing-bucket'))
    d = s3.signed_upload_url(
        path='testing/',
        filename='test.png',
        content_type='image/png',
        size=123,
        content_disp=False,
        expires=datetime(2032, 1, 1),
    )
    assert d == {
        'url': 'https://testing-bucket.s3.testing-region.amazonaws.com/',
        'fields': {
            'Key': 'testing/test.png',
            'Content-Type': 'image/png',
            'Policy': (
                'eyJleHBpcmF0aW9uIjogIjIwMzItMDEtMDFUMDA6MDA6MDBaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiAidGVzdGluZy1id'
                'WNrZXQifSwgeyJrZXkiOiAidGVzdGluZy90ZXN0LnBuZyJ9LCB7ImNvbnRlbnQtdHlwZSI6ICJpbWFnZS9wbmcifSwgWyJjb250ZW'
                '50LWxlbmd0aC1yYW5nZSIsIDEyMywgMTIzXSwgeyJ4LWFtei1jcmVkZW50aWFsIjogInRlc3RpbmctYWNjZXNzLWtleS8yMDMyMDE'
                'wMS90ZXN0aW5nLXJlZ2lvbi9zMy9hd3M0X3JlcXVlc3QifSwgeyJ4LWFtei1hbGdvcml0aG0iOiAiQVdTNC1ITUFDLVNIQTI1NiJ9'
                'LCB7IngtYW16LWRhdGUiOiAiMjAzMjAxMDFUMDAwMDAwWiJ9XX0='
            ),
            'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
            'X-Amz-Credential': 'testing-access-key/20320101/testing-region/s3/aws4_request',
            'X-Amz-Date': '20320101T000000Z',
            'X-Amz-Signature': 'd1a0cd63d314f846291b9046ef0c253923ebff4af52bb3097558373ebf76bdb2',
        },
    }


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_download_ok(client: AsyncClient, aws: DummyServer):
    s3 = S3Client(client, S3Config('testing', 'testing', 'testing', 'testing'))
    content = await s3.download('testing.txt')
    assert content == b'this is demo file content'
    assert aws.log == [IsStr(regex=r'GET /s3/testing\.txt\?.+ > 200')]


@pytest.mark.asyncio
async def test_download_ok_file(client: AsyncClient, aws: DummyServer):
    s3 = S3Client(client, S3Config('testing', 'testing', 'testing', 'testing'))
    content = await s3.download(S3File(Key='testing.txt', LastModified=0, Size=1, ETag='x', StorageClass='x'))
    assert content == b'this is demo file content'
    assert aws.log == [IsStr(regex=r'GET /s3/testing\.txt\?.+ > 200')]


@pytest.mark.asyncio
async def test_download_error(client: AsyncClient, aws: DummyServer):
    s3 = S3Client(client, S3Config('testing', 'testing', 'testing', 'testing'))
    with pytest.raises(RequestError):
        await s3.download('missing.txt')
    assert aws.log == [IsStr(regex=r'GET /s3/missing\.txt\?.+ > 404')]


@pytest.mark.asyncio
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


def test_aws4_download_signature(client: AsyncClient, mocker):
    # example direct from docs
    # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-query-string-auth.html#query-string-auth-v4-signing-example
    mocker.patch('aioaws.core.utcnow', return_value=datetime(2013, 5, 24))
    access_key = 'AKIAIOSFODNN7EXAMPLE'
    secret_key = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
    s3 = S3Client(client, S3Config(access_key, secret_key, 'us-east-1', 'examplebucket'))
    url = s3.signed_download_url('test.txt', max_age=86400)
    assert url == (
        'https://examplebucket.s3.us-east-1.amazonaws.com/test.txt'
        '?X-Amz-Algorithm=AWS4-HMAC-SHA256'
        '&X-Amz-Credential=AKIAIOSFODNN7EXAMPLE%2F20130524%2Fus-east-1%2Fs3%2Faws4_request'
        '&X-Amz-Date=20130524T000000Z'
        '&X-Amz-Expires=86400&X-Amz-SignedHeaders=host'
        '&X-Amz-Signature=762f4fcbacec730d460b0e337f554e569e4fe98643baefad7af1276fe3084e7f'
    )
    url2 = s3.signed_download_url('test.txt', max_age=86400, version='foobar')
    assert url2 == url + '&v=foobar'


def test_aws4_upload_signature(client: AsyncClient, mocker):
    # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-post-example.html
    now = datetime(2015, 12, 29)
    mocker.patch('aioaws.core.utcnow', return_value=now)
    access_key = 'AKIAIOSFODNN7EXAMPLE'
    secret_key = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
    s3 = S3Client(client, S3Config(access_key, secret_key, 'us-east-1', 'sigv4examplebucket'))
    b64_policy = (
        'eyAiZXhwaXJhdGlvbiI6ICIyMDE1LTEyLTMwVDEyOjAwOjAwLjAwMFoiLA0KICAiY29uZGl0aW9ucyI6IFsNCiAgICB7ImJ1Y2tldCI6ICJza'
        'Wd2NGV4YW1wbGVidWNrZXQifSwNCiAgICBbInN0YXJ0cy13aXRoIiwgIiRrZXkiLCAidXNlci91c2VyMS8iXSwNCiAgICB7ImFjbCI6ICJwdW'
        'JsaWMtcmVhZCJ9LA0KICAgIHsic3VjY2Vzc19hY3Rpb25fcmVkaXJlY3QiOiAiaHR0cDovL3NpZ3Y0ZXhhbXBsZWJ1Y2tldC5zMy5hbWF6b25'
        'hd3MuY29tL3N1Y2Nlc3NmdWxfdXBsb2FkLmh0bWwifSwNCiAgICBbInN0YXJ0cy13aXRoIiwgIiRDb250ZW50LVR5cGUiLCAiaW1hZ2UvIl0s'
        'DQogICAgeyJ4LWFtei1tZXRhLXV1aWQiOiAiMTQzNjUxMjM2NTEyNzQifSwNCiAgICB7IngtYW16LXNlcnZlci1zaWRlLWVuY3J5cHRpb24iO'
        'iAiQUVTMjU2In0sDQogICAgWyJzdGFydHMtd2l0aCIsICIkeC1hbXotbWV0YS10YWciLCAiIl0sDQoNCiAgICB7IngtYW16LWNyZWRlbnRpYW'
        'wiOiAiQUtJQUlPU0ZPRE5ON0VYQU1QTEUvMjAxNTEyMjkvdXMtZWFzdC0xL3MzL2F3czRfcmVxdWVzdCJ9LA0KICAgIHsieC1hbXotYWxnb3J'
        'pdGhtIjogIkFXUzQtSE1BQy1TSEEyNTYifSwNCiAgICB7IngtYW16LWRhdGUiOiAiMjAxNTEyMjlUMDAwMDAwWiIgfQ0KICBdDQp9'
    )

    d = s3._aws_client.signed_upload_fields(now, b64_policy)
    assert d == {
        'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
        'X-Amz-Credential': 'AKIAIOSFODNN7EXAMPLE/20151229/us-east-1/s3/aws4_request',
        'X-Amz-Date': '20151229T000000Z',
        'X-Amz-Signature': '8afdbf4008c03f22c2cd3cdb72e4afbb1f6a588f3255ac628749a66d7f09699e',
    }


@pytest.mark.asyncio
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
                'last_modified': IsNow(delta=10, tz='utc'),
                'size': 14,
                'e_tag': '54b0c58c7ce9f2a8b551351102ee0938',
                'storage_class': 'STANDARD',
            }
        finally:
            assert await s3.delete(path) == [path]
            assert [f.dict() async for f in s3.list(f'{run_prefix}/')] == []


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_real_many(real_aws: AWS):
    async with AsyncClient(timeout=30) as client:
        s3 = S3Client(client, S3Config(real_aws.access_key, real_aws.secret_key, 'us-east-1', 'aioaws-testing'))

        # upload many files
        await asyncio.gather(*[s3.upload(f'{run_prefix}/f_{i}.txt', f'file {i}'.encode()) for i in range(51)])

        deleted_files = await s3.delete_recursive(f'{run_prefix}/')
        assert len(deleted_files) == 51


@pytest.mark.asyncio
async def test_bad_auth():
    async with AsyncClient(timeout=30) as client:
        s3 = S3Client(client, S3Config('BAD_access_key', 'BAD_secret_key', 'us-west-2', 'foobar'))

        with pytest.raises(RequestError) as exc_info:
            await s3.upload('foobar.txt', b'hello')

        msg = exc_info.value.args[0]
        assert msg == 'unexpected response from POST "https://foobar.s3.us-west-2.amazonaws.com/": 403'
        assert str(exc_info.value).startswith(exc_info.value.args[0] + ', response:\n<?xml ')

        with pytest.raises(RequestError, match=r'POST "https://foobar.s3.us-west-2.amazonaws.com\?delete=1"'):
            await s3.delete('foobar.txt')
