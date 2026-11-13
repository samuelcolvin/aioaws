from xml.etree import ElementTree

import pytest
from httpx2 import AsyncClient, MockTransport, Response

from aioaws.s3 import S3Client, S3Config


@pytest.mark.parametrize('key', ['reports/a&b.txt', 'reports/<draft>.txt', 'reports/line\rbreak.txt'])
async def test_delete_preserves_xml_sensitive_keys(key):
    def handle(request):
        root = ElementTree.fromstring(request.content)
        assert root.find('{*}Object/{*}Key').text == key
        return Response(200, content=b'<DeleteResult/>')

    async with AsyncClient(transport=MockTransport(handle)) as client:
        s3 = S3Client(client, S3Config('testing', 'testing', 'us-east-1', 'test-bucket'))
        assert await s3.delete(key) == []
