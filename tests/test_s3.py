from datetime import datetime

from aioaws import S3Client
from aioaws.config import S3Config


def tests_upload_url():
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
