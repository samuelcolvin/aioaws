import pytest
from httpx import AsyncClient

from aioaws import _types, _utils, core


def test_get_config_attr():
    class Foo:
        a = 'alpha'
        b = 2

    f = Foo()

    assert _utils.get_config_attr(f, 'a') == 'alpha'
    with pytest.raises(TypeError, match='config has not attribute foobar'):
        _utils.get_config_attr(f, 'foobar')
    with pytest.raises(TypeError, match='config.b must be a string not int'):
        _utils.get_config_attr(f, 'b')


def test_types():
    assert hasattr(_types, 'BaseConfigProtocol')
    assert hasattr(_types, 'S3ConfigProtocol')


@pytest.mark.asyncio
async def test_response_error_xml(client: AsyncClient):
    response = await client.get(f'http://localhost:{client.port}/xml-error/')
    assert response.status_code == 456
    e = core.RequestError(response)
    assert str(e).endswith('(XML formatted by aioaws)')


@pytest.mark.asyncio
async def test_response_error_not_xml(client: AsyncClient):
    response = await client.get(f'http://localhost:{client.port}/status/400/')
    assert response.status_code == 400
    e = core.RequestError(response)
    assert str(e) == (
        f'unexpected response from GET "http://localhost:{client.port}/status/400/": 400, response:\n'
        'test response with status 400'
    )
