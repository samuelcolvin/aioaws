from dataclasses import dataclass
from datetime import datetime

from aioaws import S3Client


@dataclass
class Settings:
    aws_access_key: str = 'testing'
    aws_secret_key: str = 'testing'

    aws_s3_bucket: str = 'testing'
    aws_s3_region: str = 'testing'

    aws_ses_region: str = 'testing'


def tests_upload_url():
    s3 = S3Client('-', Settings())
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
