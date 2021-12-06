import asyncio
import base64
import json
import os
from dataclasses import dataclass, field

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
        elif url.host.startswith('sns.'):
            if 'bad' in url.path:
                return new_url.copy_with(path='/status/400/')
            elif url.path.endswith('.pem'):
                return new_url.copy_with(path='/sns/certs/')
            else:
                return new_url.copy_with(path='/status/200/')
        else:
            # return url
            raise ValueError(f'no local endpoint found for "{url}"')


@pytest.fixture(name='client')
async def _fix_client(loop, aws: DummyServer):
    async with CustomAsyncClient(local_server=aws.server_name) as client:
        yield client


default_signature = base64.b64encode(b'testing').decode()


@pytest.fixture(name='build_sns_webhook')
def _fix_build_sns_webhook(mocker):
    mocker.patch('aioaws.sns.x509.load_pem_x509_certificate')

    def build(
        message,
        *,
        event_type='Notification',
        signature=default_signature,
        sig_url='https://sns.eu-west-2.amazonaws.com/sns-123.pem',
    ):
        if not isinstance(message, str):
            message = json.dumps(message)
        d = {
            'Type': event_type,
            'SigningCertURL': sig_url,
            'Signature': signature,
            'Message': message,
        }
        return json.dumps(d)

    return build


@dataclass
class AWS:
    access_key: str
    secret_key: str = field(repr=False)
    session_token: str = field(repr=False, default='')


@pytest.fixture(
    name='real_aws',
    params=(
        ('TEST_AWS_ACCESS_KEY', 'TEST_AWS_SECRET_KEY', ''),
        ('TEST_AWS_SESSION_ACCESS_KEY', 'TEST_AWS_SESSION_SECRET_KEY', 'TEST_AWS_SESSION_TOKEN'),
    ),
)
def _fix_real_aws(request):
    access_key_variable_name, secret_key_variable_name, session_token_variable_name = request.param
    access_key = os.getenv(access_key_variable_name)
    secret_key = os.getenv(secret_key_variable_name)
    session_token = os.getenv(session_token_variable_name) if session_token_variable_name else ''
    if (access_key and secret_key) and session_token is not None:
        return AWS(access_key, secret_key, session_token)
    else:
        pytest.skip('requires TEST_AWS_ACCESS_KEY & TEST_AWS_SECRET_KEY env var')


@pytest.fixture(name='real_aws_s3_bucket_name')
def _fix_real_aws_s3_bucket_name():
    """
    Configure AWS S3 bucket name for testing.

    A configurable S3 bucket name enables contributors to run tests on their forks
    and in their AWS accounts, by setting `${{ secrets.TEST_AWS_S3_BUCKET_NAME }}`
    for GitHub Actions. Defaults to `aioaws-testing`.

    The function is written with an if expression instead of using `os.getenv` with a
    default value (`os.getenv('TEST_AWS_S3_BUCKET_NAME', 'aioaws-testing')`) because
    of how the environment variable value is passed in from GitHub Actions. If
    `${{ secrets.TEST_AWS_S3_BUCKET_NAME }}` is not set, `TEST_AWS_S3_BUCKET_NAME`
    will be an empty string, and `os.getenv('TEST_AWS_S3_BUCKET_NAME', 'aioaws-testing')`
    will return an empty string.
    """
    return value if (value := os.getenv('TEST_AWS_S3_BUCKET_NAME')) else 'aioaws-testing'


@pytest.fixture(name='real_aws_ses_address')
def _fix_real_aws_ses_address():
    """
    Configure AWS SES email address for testing.

    As with the S3 bucket name, enabling configuration of the email address allows
    contributors to run tests on their forks and in their AWS accounts, by setting
    `${{ secrets.TEST_AWS_SES_ADDRESS }}` on GitHub. Defaults to `testing@scolvin.com`.
    """
    return value if (value := os.getenv('TEST_AWS_SES_ADDRESS')) else 'testing@scolvin.com'
