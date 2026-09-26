import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import TracebackType
from unittest.mock import AsyncMock, Mock

from identity.application.commands.refresh_access_token.command import (
    RefreshAccessTokenCommand,
)
from identity.application.commands.refresh_access_token.handler import (
    RefreshAccessTokenHandler,
)
from identity.application.commands.refresh_access_token.result import (
    RefreshAccessTokenResult,
)
from identity.application.messages.base import OutboxMessage
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.application.ports.security.access_token_issuer import (
    AccessTokenIssuer,
    IssuedAccessToken,
)
from identity.application.ports.security.refresh_token_issuer import (
    IssuedRefreshToken,
    RefreshTokenIssuer,
)
from identity.application.ports.security.refresh_token_verifier import (
    RefreshTokenClaims,
    RefreshTokenVerifier,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)
from tests.unit.application.factories import make_employee

NOW = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
OLD_TOKEN = "old-refresh-secret"
NEW_TOKEN = "new-refresh-secret"
OLD_HASH = RefreshTokenHash("old-hash")
NEW_HASH = RefreshTokenHash("new-hash")


@dataclass
class MutableClock:
    current_time: datetime = NOW

    def now(self) -> datetime:
        return self.current_time


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
    repository.save.side_effect = save
    repository.list_used_refresh_token_hashes.side_effect = list_used_refresh_token_hashes
    repository.add_used_refresh_token_hash.side_effect = add_used_refresh_token_hash
    return repository


@dataclass
class RefreshContext:
    handler: RefreshAccessTokenHandler
    store: TransactionalStore
    uow: TransactionalUnitOfWork
    session_id: RefreshSessionId
    employee: EmployeeAccount
    sessions: AsyncMock
    employees: AsyncMock
    verifier: Mock
    outbox: AsyncMock
    access_issuer: Mock
    refresh_issuer: Mock
    clock: MutableClock

    @property
    def session(self) -> RefreshSession:
        return self.store.state.sessions[self.session_id]

    def execute(self, token: str = OLD_TOKEN) -> RefreshAccessTokenResult:
        return asyncio.run(self.handler.execute(RefreshAccessTokenCommand(token)))

    def assert_no_issue_or_commit(self) -> None:
        self.access_issuer.issue.assert_not_called()
        self.refresh_issuer.issue.assert_not_called()
        self.sessions.save.assert_not_awaited()
        self.sessions.add_used_refresh_token_hash.assert_not_awaited()
        self.outbox.add.assert_not_awaited()
        assert self.uow.commit_count == 0


def make_context(
    *,
    status: EmployeeStatus = EmployeeStatus.ACTIVE,
    expires_at: datetime = NOW + timedelta(days=1),
    employee: EmployeeAccount | None = None,
    store: TransactionalStore | None = None,
) -> RefreshContext:
    employee = employee or make_employee("employee@example.com", status=status)
    if store is None:
        session = RefreshSession.start(
            session_id=RefreshSessionId.new(),
            employee_id=employee.id,
            refresh_token_hash=OLD_HASH,
            created_at=NOW - timedelta(hours=1),
            expires_at=expires_at,
        )
        store = TransactionalStore(SessionState(sessions={session.id: session}))
    else:
        session = next(iter(store.state.sessions.values()))

    uow = TransactionalUnitOfWork(store)
    sessions = make_session_repository(store, uow)
    employees = AsyncMock(spec=EmployeeRepository)
    employees.get_by_id.return_value = employee

    async def add_message(message: OutboxMessage) -> None:
        store.state.messages.append(message)

    outbox = AsyncMock(spec=OutboxRepository)
    outbox.add.side_effect = add_message

    token_hashes = {OLD_TOKEN: OLD_HASH, NEW_TOKEN: NEW_HASH}
    verifier = Mock(spec=RefreshTokenVerifier)
    verifier.verify.return_value = RefreshTokenClaims(
        session_id=session.id,
        expires_at=NOW + timedelta(days=1),
    )
    verifier.matches_hash.side_effect = (
        lambda token, hashed: token_hashes.get(token) == hashed
    )

    access_issuer = Mock(spec=AccessTokenIssuer)
    access_issuer.issue.return_value = IssuedAccessToken(
        plain_token="access-secret",
        expires_at=NOW + timedelta(minutes=10),
    )
    refresh_issuer = Mock(spec=RefreshTokenIssuer)
    refresh_issuer.issue.return_value = IssuedRefreshToken(
        plain_token=NEW_TOKEN,
        token_hash=NEW_HASH,
    )
    clock = MutableClock()

    handler = RefreshAccessTokenHandler(
        uow=uow,
        clock=clock,
        refresh_session_repository=sessions,
        employee_repository=employees,
        access_token_issuer=access_issuer,
        refresh_token_issuer=refresh_issuer,
        refresh_token_verifier=verifier,
        outbox_repository=outbox,
    )
    return RefreshContext(
        handler=handler,
        store=store,
        uow=uow,
        session_id=session.id,
        employee=employee,
        sessions=sessions,
        employees=employees,
        verifier=verifier,
        outbox=outbox,
        access_issuer=access_issuer,
        refresh_issuer=refresh_issuer,
        clock=clock,
    )
