import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from identity.infrastructure.persistence.models import Base
from identity.infrastructure.rate_limit.limits import RateLimit, RateLimitExceededError
from identity.infrastructure.rate_limit.postgres_rate_limiter import (
    COUNTER_RETENTION,
    PostgresRateLimiter,
)
from tests.unit.application.doubles import FixedClock

NOW = datetime(2026, 11, 1, 12, 0, 30, tzinfo=timezone.utc)
LIMIT = RateLimit("login:email", 3, timedelta(minutes=1))


def _sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()


class FakeSessionFactory:
    def __init__(self, stored_hits: int | None = None) -> None:
        self.session = MagicMock()
        self.session.scalar = AsyncMock(return_value=stored_hits)
        self.session.execute = AsyncMock()
        self.session.commit = AsyncMock()
        self.session.__aenter__ = AsyncMock(return_value=self.session)
        self.session.__aexit__ = AsyncMock(return_value=None)

    def __call__(self):
        return self.session


def test_window_start_is_aligned_to_window() -> None:
    assert LIMIT.window_start(NOW) == datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    assert LIMIT.retry_after(NOW) == 30
    assert LIMIT.retry_after(NOW + timedelta(seconds=29, microseconds=500)) == 1


def test_key_hash_hides_subject_and_separates_limits() -> None:
    other = RateLimit("token:client", 3, timedelta(minutes=1))

    key_hash = LIMIT.key_hash("user@example.com")

    assert len(key_hash) == 64
    assert "example" not in key_hash
    assert key_hash != other.key_hash("user@example.com")
    assert key_hash != LIMIT.key_hash("other@example.com")


@pytest.mark.parametrize(
    ("limit", "window"),
    [(0, timedelta(minutes=1)), (1, timedelta(0))],
)
def test_rate_limit_must_be_positive(limit: int, window: timedelta) -> None:
    with pytest.raises(ValueError):
        RateLimit("name", limit, window)


def test_ensure_allowed_passes_below_limit() -> None:
    factory = FakeSessionFactory(stored_hits=2)
    limiter = PostgresRateLimiter(factory, FixedClock(NOW))

    asyncio.run(limiter.ensure_allowed((LIMIT, "user@example.com")))

    sql = _sql(factory.session.scalar.call_args.args[0])
    assert LIMIT.key_hash("user@example.com") in sql
    assert "user@example.com" not in sql
    assert "2026-11-01 12:00:00" in sql


@pytest.mark.parametrize("stored_hits", [3, 10])
def test_ensure_allowed_rejects_at_limit_with_retry_after(stored_hits: int) -> None:
    limiter = PostgresRateLimiter(FakeSessionFactory(stored_hits), FixedClock(NOW))

    with pytest.raises(RateLimitExceededError) as error:
        asyncio.run(limiter.ensure_allowed((LIMIT, "user@example.com")))

    assert error.value.retry_after == 30


def test_no_counter_means_allowed() -> None:
    limiter = PostgresRateLimiter(FakeSessionFactory(None), FixedClock(NOW))

    asyncio.run(limiter.ensure_allowed((LIMIT, "user@example.com")))


def test_record_upserts_counter_purges_old_rows_and_commits() -> None:
    factory = FakeSessionFactory()
    limiter = PostgresRateLimiter(factory, FixedClock(NOW))

    asyncio.run(limiter.record((LIMIT, "user@example.com")))

    upsert, purge = (call.args[0] for call in factory.session.execute.call_args_list)
    upsert_sql = _sql(upsert)
    assert upsert_sql.startswith("insert into rate_limit_counter")
    assert "on conflict (key_hash, window_start) do update" in upsert_sql
    assert "hits = (rate_limit_counter.hits + 1)" in upsert_sql
    purge_sql = _sql(purge)
    assert purge_sql.startswith("delete from rate_limit_counter")
    assert str((NOW - COUNTER_RETENTION).date()) in purge_sql
    factory.session.commit.assert_awaited_once()


def test_rate_limit_counter_table_stores_only_hashes() -> None:
    table = Base.metadata.tables["rate_limit_counter"]

    assert list(table.primary_key.columns.keys()) == ["key_hash", "window_start"]
    assert set(table.c.keys()) == {"key_hash", "window_start", "hits"}
