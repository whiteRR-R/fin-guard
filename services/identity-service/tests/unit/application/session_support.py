import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from unittest.mock import AsyncMock

from identity.application.messages.base import OutboxMessage
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)


@dataclass
class SessionState:
    sessions: dict[RefreshSessionId, RefreshSession] = field(default_factory=dict)
    history: dict[RefreshSessionId, list[RefreshTokenHash]] = field(default_factory=dict)
    messages: list[OutboxMessage] = field(default_factory=list)


@dataclass
class TransactionalStore:
    state: SessionState
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TransactionalUnitOfWork:
    def __init__(self, store: TransactionalStore) -> None:
        self.store = store
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_commit = False
        self._snapshot: SessionState | None = None
        self._committed = False
        self._entered = False

    async def __aenter__(self) -> "TransactionalUnitOfWork":
        self._entered = True
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None or not self._committed:
                await self.rollback()
        finally:
            if self._snapshot is not None:
                self.store.lock.release()
            self._snapshot = None
            self._entered = False

    async def lock_session(self) -> None:
        assert self._entered
        assert self._snapshot is None
        await self.store.lock.acquire()
        self._snapshot = deepcopy(self.store.state)

    async def commit(self) -> None:
        assert self._snapshot is not None
        if self.fail_commit:
            raise RuntimeError("Commit failed")
        self.commit_count += 1
        self._committed = True

    async def rollback(self) -> None:
        if self._snapshot is not None:
            self.store.state = self._snapshot
        self.rollback_count += 1


def make_session_repository(
    store: TransactionalStore,
    uow: TransactionalUnitOfWork,
) -> AsyncMock:
    async def get_with_lock(session_id: RefreshSessionId) -> RefreshSession | None:
        await uow.lock_session()
        await asyncio.sleep(0)
        return store.state.sessions.get(session_id)

    async def save(session: RefreshSession) -> None:
        store.state.sessions[session.id] = session

    async def list_active_by_employee_with_lock(
        employee_id: EmployeeId,
        *,
        active_at: datetime,
    ) -> list[RefreshSession]:
        await uow.lock_session()
        await asyncio.sleep(0)
        return [
            session
            for session in store.state.sessions.values()
            if session.employee_id == employee_id and session.is_active(active_at)
        ]

    async def list_used_refresh_token_hashes(
        session_id: RefreshSessionId,
    ) -> tuple[RefreshTokenHash, ...]:
        return tuple(store.state.history.get(session_id, ()))

    async def add_used_refresh_token_hash(
        session_id: RefreshSessionId,
        token_hash: RefreshTokenHash,
    ) -> None:
        store.state.history.setdefault(session_id, []).append(token_hash)

    repository = AsyncMock(spec=RefreshSessionRepository)
    repository.get_by_id_with_lock.side_effect = get_with_lock
    repository.list_active_by_employee_with_lock.side_effect = (
        list_active_by_employee_with_lock
    )
    repository.save.side_effect = save
    repository.list_used_refresh_token_hashes.side_effect = list_used_refresh_token_hashes
    repository.add_used_refresh_token_hash.side_effect = add_used_refresh_token_hash
    return repository
