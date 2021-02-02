import pytest

from aioaws import _types, _utils


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
