import asyncio
import base64
import json

import pytest
from foxglove.test_server import DummyServer, create_dummy_server
from httpx import URL, AsyncClient

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
        if isinstance(url, str):
            if url.startswith('http://localhost'):
                return url
            url = URL(url)

        new_url = url.copy_with(scheme=self.scheme, host=self.host, port=self.port)
        if 's3.' in url.host:
            return new_url.copy_with(path='/s3/')
        elif 'email.' in url.host:
            return new_url.copy_with(path='/ses/')
        elif url.host.startswith('sns.') and url.path.endswith('.pem'):
            return new_url.copy_with(path='/sns/certs/')
        elif url.host.startswith('sns.'):
            return new_url.copy_with(path='/status/200/')
        else:
            # return url
            raise ValueError(f'no local endpoint found for "{url}"')


@pytest.fixture(name='client')
async def _fix_client(loop, aws: DummyServer):
    async with CustomAsyncClient(local_server=aws.server_name) as client:
        yield client


@pytest.fixture(name='build_sns_webhook')
def _fix_build_sns_webhook(mocker):
    mocker.patch('aioaws.sns.x509.load_pem_x509_certificate')

    def build(message, *, event_type='Notification', sig_url='https://sns.eu-west-2.amazonaws.com/sns-123.pem'):
        if not isinstance(message, str):
            message = json.dumps(message)
        d = {
            'Type': event_type,
            'SigningCertURL': sig_url,
            'Signature': base64.b64encode(b'testing').decode(),
            'Message': message,
        }
        return json.dumps(d)

    return build
