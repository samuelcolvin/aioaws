import asyncio

import pytest
from foxglove.test_server import DummyServer, create_dummy_server
from httpx import AsyncClient

from . import dummy_server


@pytest.fixture(name='loop')
def _fix_loop():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


@pytest.fixture(name='aws')
def _fix_aws(loop):
    ctx = {'s3_files': {}, 'emails': []}
    ds = loop.run_until_complete(create_dummy_server(loop, extra_routes=dummy_server.routes, extra_context=ctx))
    yield ds
    loop.run_until_complete(ds.stop())


class CustomAsyncClient(AsyncClient):
    def __init__(self, *args, local_server, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheme, host_port = local_server.split('://')
        self.host, port = host_port.split(':')
        self.port = int(port)

    def _merge_url(self, url):
        new_url = url.copy_with(scheme=self.scheme, host=self.host, port=self.port)
        if 's3.' in url.host:
            new_url = new_url.copy_with(path='/s3/')
        elif 'email.' in url.host:
            new_url = new_url.copy_with(path='/ses/')
        return new_url


@pytest.fixture(name='client')
async def _fix_client(loop, aws: DummyServer):
    async with CustomAsyncClient(local_server=aws.server_name) as client:
        yield client
