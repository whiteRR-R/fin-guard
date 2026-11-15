from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.ports.clock import Clock
from identity.infrastructure.persistence.models.rate_limit_counter import (
    RateLimitCounterModel,
)
from identity.infrastructure.rate_limit.limits import RateLimit, RateLimitExceededError

COUNTER_RETENTION = timedelta(days=1)


class PostgresRateLimiter:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Clock,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def ensure_allowed(self, *checks: tuple[RateLimit, str]) -> None:
        now = self._clock.now()
        async with self._session_factory() as session:
            for rate_limit, subject in checks:
                hits = await session.scalar(
                    select(RateLimitCounterModel.hits).where(
                        RateLimitCounterModel.key_hash == rate_limit.key_hash(subject),
                        RateLimitCounterModel.window_start
                        == rate_limit.window_start(now),
                    )
                )
                if hits is not None and hits >= rate_limit.limit:
                    raise RateLimitExceededError(rate_limit.retry_after(now))

    async def record(self, *hits: tuple[RateLimit, str]) -> None:
        now = self._clock.now()
        async with self._session_factory() as session:
            for rate_limit, subject in hits:
                statement = insert(RateLimitCounterModel).values(
                    key_hash=rate_limit.key_hash(subject),
                    window_start=rate_limit.window_start(now),
                    hits=1,
                )
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[
                            RateLimitCounterModel.key_hash,
                            RateLimitCounterModel.window_start,
                        ],
                        set_={"hits": RateLimitCounterModel.hits + 1},
                    )
                )
            await session.execute(
                delete(RateLimitCounterModel).where(
                    RateLimitCounterModel.window_start < now - COUNTER_RETENTION
                )
            )
            await session.commit()
