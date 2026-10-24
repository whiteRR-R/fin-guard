import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

from identity.application.commands.revoke_own_session.command import (
    RevokeOwnSessionCommand,
)
from identity.application.commands.revoke_own_session.handler import (
    RevokeOwnSessionHandler,
)
from identity.application.messages.base import OutboxMessage
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.queries.list_own_sessions.handler import (
    ListOwnSessionsHandler,
)
from identity.application.queries.list_own_sessions.query import ListOwnSessionsQuery
from identity.application.queries.list_own_sessions.result import ListOwnSessionsResult
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.value_objects.employee_id import EmployeeId
from tests.unit.application.doubles import UnitOfWorkFake
from tests.unit.application.factories import make_employee, make_refresh_session
from tests.unit.application.session_support import (
    SessionState,
    TransactionalStore,
    TransactionalUnitOfWork,
    make_session_repository,
)

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


@dataclass
class OwnSessionsContext:
    revoke_handler: RevokeOwnSessionHandler
    list_handler: ListOwnSessionsHandler
    employee: EmployeeAccount
    current_session: RefreshSession
    target_session: RefreshSession
    other_session: RefreshSession
    foreign_session: RefreshSession
    store: TransactionalStore
    revoke_uow: TransactionalUnitOfWork
    list_uow: UnitOfWorkFake
    sessions: AsyncMock
    outbox: AsyncMock
    clock: Mock

    @property
    def command(self) -> RevokeOwnSessionCommand:
        return RevokeOwnSessionCommand(
            employee_id=self.employee.id.value,
            target_session_id=self.target_session.id.value,
        )

    @property
    def query(self) -> ListOwnSessionsQuery:
        return ListOwnSessionsQuery(
            employee_id=self.employee.id.value,
            current_session_id=self.current_session.id.value,
        )

    def revoke(self, command: RevokeOwnSessionCommand | None = None) -> None:
        asyncio.run(self.revoke_handler.execute(command or self.command))

    def list_sessions(self) -> ListOwnSessionsResult:
        return asyncio.run(self.list_handler.execute(self.query))


def make_context() -> OwnSessionsContext:
    employee = make_employee("employee@example.com")
    current = make_refresh_session(employee.id, now=NOW - timedelta(minutes=30))
    target = make_refresh_session(employee.id, now=NOW - timedelta(minutes=10))
    other = make_refresh_session(employee.id, now=NOW - timedelta(minutes=20))
    foreign = make_refresh_session(EmployeeId.new(), now=NOW)
    store = TransactionalStore(
        SessionState(sessions={s.id: s for s in (current, target, other, foreign)})
    )
    revoke_uow = TransactionalUnitOfWork(store)
    list_uow = UnitOfWorkFake()
    sessions = make_session_repository(store, revoke_uow)
    clock = Mock(spec=Clock)
    clock.now.return_value = NOW

    async def list_active(employee_id: EmployeeId) -> list[RefreshSession]:
        return [
            session
            for session in store.state.sessions.values()
            if session.employee_id == employee_id
            and session.is_active(clock.now())
        ]

    async def add_message(message: OutboxMessage) -> None:
        store.state.messages.append(message)

    sessions.list_active_by_employee.side_effect = list_active
    sessions.get_by_id.side_effect = lambda session_id: store.state.sessions.get(
        session_id
    )
    outbox = AsyncMock(spec=OutboxRepository)
    outbox.add.side_effect = add_message
    revoke_handler = RevokeOwnSessionHandler(
        uow=revoke_uow,
        clock=clock,
        refresh_session_repository=sessions,
        outbox_repository=outbox,
    )
    list_handler = ListOwnSessionsHandler(
        uow=list_uow,
        clock=clock,
        refresh_session_repository=sessions,
    )
    return OwnSessionsContext(
        revoke_handler=revoke_handler,
        list_handler=list_handler,
        employee=employee,
        current_session=current,
        target_session=target,
        other_session=other,
        foreign_session=foreign,
        store=store,
        revoke_uow=revoke_uow,
        list_uow=list_uow,
        sessions=sessions,
        outbox=outbox,
        clock=clock,
    )
