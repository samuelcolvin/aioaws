import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Iterable, List, Optional

__all__ = 'get_config_attr', 'to_unix_s', 'utcnow', 'ManyTasks'

if TYPE_CHECKING:
    from ._types import BaseConfigProtocol


EPOCH = datetime(1970, 1, 1)
EPOCH_TZ = EPOCH.replace(tzinfo=timezone.utc)


def get_config_attr(config: 'BaseConfigProtocol', name: str) -> str:
    try:
        s = getattr(config, name)
    except AttributeError:
        raise TypeError(f'config has not attribute {name}')

    if isinstance(s, str):
        return s
    else:
        raise TypeError(f'config.{name} must be a string not {s.__class__.__name__}')


def to_unix_s(dt: datetime) -> int:
    if dt.utcoffset() is None:
        diff = dt - EPOCH
    else:
        diff = dt - EPOCH_TZ
    return int(round(diff.total_seconds()))


def utcnow() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)


class ManyTasks:
    """
    Simply utility to start many tasks without awaiting them, then wait for them all to finish
    """

    __slots__ = '_tasks'

    def __init__(self) -> None:
        self._tasks: List[asyncio.Task[Any]] = []

    def add(self, coroutine: Awaitable[Any], *, name: Optional[str] = None) -> None:
        task = asyncio.create_task(coroutine, name=name)
        self._tasks.append(task)

    async def finish(self) -> Iterable[Any]:
        return await asyncio.gather(*self._tasks)
