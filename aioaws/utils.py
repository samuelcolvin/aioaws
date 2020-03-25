import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Iterable, List, Optional, Protocol

__all__ = 'Settings', 'to_unix_s', 'utcnow', 'ManyTasks'


class Settings(Protocol):
    aws_access_key: str
    aws_secret_key: str

    aws_s3_bucket: str
    aws_s3_region: str

    aws_ses_region: str


EPOCH = datetime(1970, 1, 1)
EPOCH_TZ = EPOCH.replace(tzinfo=timezone.utc)


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
