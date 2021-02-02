from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from pytest_toolbox.comparison import CloseToNow

from aioaws.s3 import S3Client, S3Config

from .conftest import AWS

pytestmark = pytest.mark.asyncio


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


async def test_list(client: AsyncClient):
    s3 = S3Client(client, S3Config('testing', 'testing', 'testing', 'testing'))
    files = [f async for f in s3.list()]
    assert len(files) == 3
    assert files[0].dict() == dict(
        key='foo/bar/1.png',
        last_modified=datetime(2032, 1, 1, 12, 34, 56, tzinfo=timezone.utc),
        size=123,
        e_tag='aaa',
        storage_class='STANDARD',
    )


async def test_real_upload(real_aws: AWS):
    async with AsyncClient() as client:
        s3 = S3Client(client, S3Config(real_aws.access_key, real_aws.secret_key, 'us-east-1', 'aioaws-testing'))

        await s3.upload('testing/test.txt', b'this is a test')

        files = [f.dict() async for f in s3.list()]
        # debug(files)
        assert files == [
            {
                'key': 'testing/test.txt',
                'last_modified': CloseToNow(delta=10),
                'size': 14,
                'e_tag': '54b0c58c7ce9f2a8b551351102ee0938',
                'storage_class': 'STANDARD',
            },
        ]

        await s3.delete('testing/test.txt')
        await s3.delete('testing/text.txt')

        assert [f.dict() async for f in s3.list()] == []
