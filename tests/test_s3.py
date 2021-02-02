from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from aioaws.s3 import S3Client, S3Config

from .conftest import AWS

pytestmark = pytest.mark.asyncio


def test_upload_url():
    s3 = S3Client('-', S3Config('testing', 'testing', 'testing', 'testing'))
    d = s3.signed_upload_url(
        path='testing/', filename='test.png', content_type='image/png', size=123, expires=datetime(2032, 1, 1)
    )
    assert d == {
        'url': 'https://testing/',
        'fields': {
            'Key': 'testing/test.png',
            'Content-Type': 'image/png',
            'AWSAccessKeyId': 'testing',
            'Content-Disposition': 'attachment; filename="test.png"',
            'Policy': (
                'eyJleHBpcmF0aW9uIjogIjIwMzItMDEtMDFUMDA6MDA6MDBaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiOiAidGVzdGluZyJ9L'
                'CB7ImtleSI6ICJ0ZXN0aW5nL3Rlc3QucG5nIn0sIHsiY29udGVudC10eXBlIjogImltYWdlL3BuZyJ9LCBbImNvbnRlbnQtbGVuZ3'
                'RoLXJhbmdlIiwgMTIzLCAxMjNdLCB7IkNvbnRlbnQtRGlzcG9zaXRpb24iOiAiYXR0YWNobWVudDsgZmlsZW5hbWU9XCJ0ZXN0LnB'
                'uZ1wiIn1dfQ=='
            ),
            'Signature': 'gT3B054t0xopAJpy1JYq6678xN8=',
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
        s3 = S3Client(client, S3Config(real_aws.access_key, real_aws.secret_key, 'us-west-1', 'aioaws-testing'))

        content = b'this is a test'
        d = s3.signed_upload_url(
            path='testing/',
            filename='test.txt',
            content_type='text/plain',
            size=len(content),
            expires=datetime.now() + timedelta(hours=1),
        )
        debug(d)
