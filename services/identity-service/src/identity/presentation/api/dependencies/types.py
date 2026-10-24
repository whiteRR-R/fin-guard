from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession


T = TypeVar("T")
Provider = Callable[..., Awaitable[T]]
SessionProvider = Callable[..., AsyncIterator[AsyncSession]]
