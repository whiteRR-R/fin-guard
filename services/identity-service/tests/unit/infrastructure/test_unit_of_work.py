import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork


def test_commit_is_explicit() -> None:
    session = AsyncMock(spec=AsyncSession)
    uow = SqlAlchemyUnitOfWork(session)

    async def run() -> None:
        async with uow:
            session.commit.assert_not_awaited()
            await uow.commit()

    asyncio.run(run())

    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()
    session.close.assert_not_awaited()


def test_exit_without_commit_rolls_back() -> None:
    session = AsyncMock(spec=AsyncSession)
    uow = SqlAlchemyUnitOfWork(session)

    async def run() -> None:
        async with uow:
            pass

    asyncio.run(run())

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


def test_exception_rolls_back_and_propagates() -> None:
    session = AsyncMock(spec=AsyncSession)
    uow = SqlAlchemyUnitOfWork(session)

    async def run() -> None:
        async with uow:
            raise ValueError("write failed")

    with pytest.raises(ValueError, match="write failed"):
        asyncio.run(run())

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


def test_failed_commit_rolls_back() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.commit.side_effect = RuntimeError("database unavailable")
    uow = SqlAlchemyUnitOfWork(session)

    async def run() -> None:
        async with uow:
            await uow.commit()

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(run())

    session.rollback.assert_awaited_once_with()
