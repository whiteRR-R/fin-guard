import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from identity.application.authentication.authenticate_access_token import (
    AuthenticateAccessToken,
)
from identity.application.commands.logout.command import LogoutCommand
from identity.application.commands.logout.handler import LogoutHandler
from identity.application.commands.refresh_access_token.command import (
    RefreshAccessTokenCommand,
)
from identity.application.commands.refresh_access_token.result import (
    RefreshAccessTokenResult,
)
from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    SessionIsNotActiveError,
    SessionNotFoundError,
)
from identity.application.messages.base import OutboxMessage
from identity.application.messages.session_logged_out import SessionLoggedOut
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.security.access_token_verifier import (
    AccessTokenClaims,
    AccessTokenVerifier,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import RefreshSessionId
from tests.unit.application.doubles import UnitOfWorkFake
from tests.unit.application.factories import make_employee, make_refresh_session
from tests.unit.application.refresh_access_token_support import (
    OLD_TOKEN,
)
from tests.unit.application.refresh_access_token_support import (
    make_context as make_refresh_context,
)
from tests.unit.application.session_support import (
    SessionState,
    TransactionalStore,
    TransactionalUnitOfWork,
    make_session_repository,
)

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
ACCESS_TOKEN = "access-token-secret"


@dataclass
class LogoutContext:
    handler: LogoutHandler
    authenticator: AuthenticateAccessToken
    employee: EmployeeAccount
    session_id: RefreshSessionId
    store: TransactionalStore
    uow: TransactionalUnitOfWork
    sessions: AsyncMock
    outbox: AsyncMock
    verifier: Mock
    clock: Mock

    @property
    def session(self) -> RefreshSession:
        return self.store.state.sessions[self.session_id]

    @property
    def command(self) -> LogoutCommand:
        return LogoutCommand(
            employee_id=self.employee.id.value,
            session_id=self.session_id.value,
        )

    def execute(self, command: LogoutCommand | None = None) -> None:
        asyncio.run(self.handler.execute(command or self.command))

    async def authenticate_and_logout(self) -> None:
        actor = await self.authenticator.execute(ACCESS_TOKEN)
        command = LogoutCommand(
            employee_id=actor.employee_id.value,
            session_id=actor.session_id.value,
        )
        await self.handler.execute(command)


@pytest.fixture
def context() -> LogoutContext:
    employee = make_employee("employee@example.com")
    session = make_refresh_session(employee.id, now=NOW)
    store = TransactionalStore(SessionState(sessions={session.id: session}))
    uow = TransactionalUnitOfWork(store)
    sessions = make_session_repository(store, uow)
    clock = Mock(spec=Clock)
    clock.now.return_value = NOW
    verifier = Mock(spec=AccessTokenVerifier)
    verifier.verify.return_value = AccessTokenClaims(
        employee_id=employee.id,
        sid=session.id,
        roles=employee.roles,
        expires_at=NOW + timedelta(minutes=10),
    )

    async def add_message(message: OutboxMessage) -> None:
        store.state.messages.append(message)

    outbox = AsyncMock(spec=OutboxRepository)
    outbox.add.side_effect = add_message
    handler = LogoutHandler(
        uow=uow,
        clock=clock,
        refresh_session_repository=sessions,
        outbox_repository=outbox,
    )
    employees = AsyncMock(spec=EmployeeRepository)
    employees.get_by_id.return_value = employee
    sessions.get_by_id.side_effect = lambda session_id: store.state.sessions.get(
        session_id
    )
    authenticator = AuthenticateAccessToken(
        clock=clock,
        uow=UnitOfWorkFake(),
        employees=employees,
        refresh_sessions=sessions,
        access_token_verifier=verifier,
    )
    return LogoutContext(
        handler=handler,
        authenticator=authenticator,
        employee=employee,
        session_id=session.id,
        store=store,
        uow=uow,
        sessions=sessions,
        outbox=outbox,
        verifier=verifier,
        clock=clock,
    )


def test_logout_revokes_only_current_session_and_records_audit(
    context: LogoutContext,
) -> None:
    other_session = make_refresh_session(context.employee.id, now=NOW)
    context.store.state.sessions[other_session.id] = other_session

    result = context.execute()

    assert result is None
    assert context.session.revoked_at == NOW
    assert other_session.is_active(NOW)
    assert context.uow.commit_count == 1
    assert context.uow.rollback_count == 0
    context.verifier.verify.assert_not_called()
    context.sessions.get_by_id_with_lock.assert_awaited_once_with(context.session_id)
    message, = context.store.state.messages
    assert isinstance(message, SessionLoggedOut)
    assert message.employee_id == context.employee.id.value
    assert message.session_id == context.session_id.value
    assert message.created_at == NOW
    assert message.version == 1
    assert ACCESS_TOKEN not in repr(message)


def test_repeated_logout_preserves_revocation_time_and_does_not_repeat_audit(
    context: LogoutContext,
) -> None:
    context.execute()
    context.clock.now.return_value = NOW + timedelta(minutes=1)

    context.execute()

    assert context.session.revoked_at == NOW
    assert context.uow.commit_count == 1
    assert len(context.store.state.messages) == 1
    context.sessions.save.assert_awaited_once()


def test_logout_cannot_revoke_another_employees_session(context: LogoutContext) -> None:
    command = replace(context.command, employee_id=EmployeeId.new().value)

    with pytest.raises(AccessDeniedError):
        context.execute(command)

    assert context.session.revoked_at is None
    context.sessions.save.assert_not_awaited()
    context.outbox.add.assert_not_awaited()
    assert context.uow.commit_count == 0


def test_logout_rejects_missing_session(context: LogoutContext) -> None:
    context.store.state.sessions.clear()

    with pytest.raises(SessionNotFoundError):
        context.execute()

    context.sessions.save.assert_not_awaited()
    assert context.store.state.messages == []
    assert context.uow.commit_count == 0


def test_logout_rejects_invalid_token_before_loading_session(
    context: LogoutContext,
) -> None:
    context.verifier.verify.side_effect = AuthenticationError("Invalid token")

    with pytest.raises(AuthenticationError):
        asyncio.run(context.authenticate_and_logout())

    context.sessions.get_by_id_with_lock.assert_not_awaited()
    assert context.uow.commit_count == 0


def test_logout_rejects_expired_access_token(context: LogoutContext) -> None:
    context.verifier.verify.return_value = replace(
        context.verifier.verify.return_value,
        expires_at=NOW,
    )

    with pytest.raises(AuthenticationError, match="expired"):
        asyncio.run(context.authenticate_and_logout())

    assert context.session.revoked_at is None
    context.sessions.save.assert_not_awaited()
    assert context.uow.commit_count == 0


@pytest.mark.parametrize("failure", ["save", "outbox", "commit"])
def test_failed_logout_rolls_back_revocation_and_audit(
    context: LogoutContext,
    failure: str,
) -> None:
    if failure == "save":
        context.sessions.save.side_effect = RuntimeError("Save failed")
    elif failure == "outbox":
        context.outbox.add.side_effect = RuntimeError("Outbox failed")
    else:
        context.uow.fail_commit = True

    with pytest.raises(RuntimeError):
        context.execute()

    assert context.session.revoked_at is None
    assert context.store.state.messages == []
    assert context.uow.commit_count == 0
    assert context.uow.rollback_count == 1


def test_authenticated_logout_uses_actor_and_prevents_further_authentication(
    context: LogoutContext,
) -> None:
    asyncio.run(context.authenticate_and_logout())

    context.verifier.verify.assert_called_once_with(ACCESS_TOKEN)
    context.sessions.get_by_id_with_lock.assert_awaited_once_with(context.session_id)
    assert context.session.revoked_at == NOW

    with pytest.raises(AuthenticationError, match="revoked"):
        asyncio.run(context.authenticate_and_logout())

    assert context.uow.commit_count == 1
    assert len(context.store.state.messages) == 1


@pytest.mark.parametrize("logout_first", [True, False])
def test_concurrent_refresh_cannot_leave_logged_out_session_active(
    context: LogoutContext,
    logout_first: bool,
) -> None:
    async def run() -> None:
        refresh = make_refresh_context(
            employee=context.employee,
            store=context.store,
        )
        refresh.clock.current_time = NOW
        refresh.verifier.verify.return_value = replace(
            refresh.verifier.verify.return_value,
            expires_at=NOW + timedelta(hours=1),
        )
        refresh.verifier.matches_hash.side_effect = None
        refresh.verifier.matches_hash.return_value = True
        logout_request = context.handler.execute(context.command)
        refresh_request = refresh.handler.execute(RefreshAccessTokenCommand(OLD_TOKEN))
        requests = (
            (logout_request, refresh_request)
            if logout_first
            else (refresh_request, logout_request)
        )

        results = await asyncio.gather(*requests, return_exceptions=True)

        logout_result = results[0 if logout_first else 1]
        refresh_result = results[1 if logout_first else 0]
        assert logout_result is None
        if logout_first:
            assert isinstance(refresh_result, SessionIsNotActiveError)
            refresh.access_issuer.issue.assert_not_called()
        else:
            assert isinstance(refresh_result, RefreshAccessTokenResult)
        assert context.session.revoked_at == NOW
        assert len(context.store.state.messages) == 1

    asyncio.run(run())
