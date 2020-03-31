import pytest
from atoolbox.test_utils import DummyServer, create_dummy_server
from httpx import AsyncClient

from . import dummy_server


@pytest.fixture(name='aws')
async def _fix_aws(loop, aiohttp_server):
    ctx = {'s3_files': {}}
    return await create_dummy_server(aiohttp_server, extra_routes=dummy_server.routes, extra_context=ctx)


class CustomAsyncClient(AsyncClient):
    def __init__(self, *args, local_server, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheme, host_port = local_server.split('://')
        self.host, self.port = host_port.split(':')

    def merge_url(self, url):
        new_url = url.copy_with(scheme=self.scheme, host=self.host, port=self.port)
        if 's3.' in url.host:
            new_url = new_url.copy_with(path='/s3/')
        return new_url


@pytest.fixture(name='client')
async def _fix_client(loop, aws: DummyServer):
    async with CustomAsyncClient(local_server=aws.server_name) as client:
        yield client
