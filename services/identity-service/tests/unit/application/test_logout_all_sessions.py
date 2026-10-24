import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from identity.application.authentication.authenticate_access_token import (
    AuthenticateAccessToken,
)
from identity.application.commands.logout_all_sessions.command import (
    LogoutAllSessionsCommand,
)
from identity.application.commands.logout_all_sessions.handler import (
    LogoutAllSessionsHandler,
)
from identity.application.commands.refresh_access_token.command import (
    RefreshAccessTokenCommand,
)
from identity.application.commands.refresh_access_token.result import (
    RefreshAccessTokenResult,
)
from identity.application.exceptions import (
    AuthenticationError,
    EmployeeNotFoundError,
    SessionIsNotActiveError,
)
from identity.application.messages.all_sessions_logged_out import AllSessionsLoggedOut
from identity.application.messages.base import OutboxMessage
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


@dataclass
class LogoutAllSessionsContext:
    handler: LogoutAllSessionsHandler
    employee: EmployeeAccount
    store: TransactionalStore
    uow: TransactionalUnitOfWork
    sessions: AsyncMock
    employees: AsyncMock
    outbox: AsyncMock
    clock: Mock

    @property
    def command(self) -> LogoutAllSessionsCommand:
        return LogoutAllSessionsCommand(employee_id=self.employee.id.value)

    def execute(self) -> None:
        asyncio.run(self.handler.execute(self.command))


@pytest.fixture
def context() -> LogoutAllSessionsContext:
    employee = make_employee("employee@example.com")
    sessions = [make_refresh_session(employee.id, now=NOW) for _ in range(2)]
    store = TransactionalStore(
        SessionState(sessions={session.id: session for session in sessions})
    )
    uow = TransactionalUnitOfWork(store)
    session_repository = make_session_repository(store, uow)
    employee_repository = AsyncMock(spec=EmployeeRepository)
    employee_repository.get_by_id.return_value = employee
    clock = Mock(spec=Clock)
    clock.now.return_value = NOW

    async def add_message(message: OutboxMessage) -> None:
        store.state.messages.append(message)

    outbox = AsyncMock(spec=OutboxRepository)
    outbox.add.side_effect = add_message
    handler = LogoutAllSessionsHandler(
        uow=uow,
        clock=clock,
        employee_repository=employee_repository,
        refresh_session_repository=session_repository,
        outbox_repository=outbox,
    )
    return LogoutAllSessionsContext(
        handler=handler,
        employee=employee,
        store=store,
        uow=uow,
        sessions=session_repository,
        employees=employee_repository,
        outbox=outbox,
        clock=clock,
    )


def test_revokes_all_own_sessions_and_preserves_other_employees_sessions(
    context: LogoutAllSessionsContext,
) -> None:
    own_sessions = tuple(context.store.state.sessions.values())
    other_employee = make_employee("other@example.com")
    other_session = make_refresh_session(other_employee.id, now=NOW)
    context.store.state.sessions[other_session.id] = other_session

    result = context.execute()

    assert result is None
    assert all(session.revoked_at == NOW for session in own_sessions)
    assert other_session.is_active(NOW)
    assert context.sessions.save.await_count == 2
    context.sessions.get_by_id.assert_not_awaited()
    context.sessions.list_active_by_employee_with_lock.assert_awaited_once_with(
        context.employee.id,
        active_at=NOW,
    )
    assert context.uow.commit_count == 1
    assert context.uow.rollback_count == 0
    (message,) = context.store.state.messages
    assert isinstance(message, AllSessionsLoggedOut)
    assert message.employee_id == context.employee.id.value
    assert message.revoked_sessions_count == 2
    assert message.created_at == NOW
    assert message.version == 1


def test_expired_and_revoked_sessions_are_not_modified(
    context: LogoutAllSessionsContext,
) -> None:
    expired = make_refresh_session(context.employee.id, now=NOW - timedelta(hours=1))
    revoked = make_refresh_session(context.employee.id, now=NOW)
    revoked_at = NOW - timedelta(minutes=5)
    revoked.revoke(revoked_at)
    context.store.state.sessions.update({expired.id: expired, revoked.id: revoked})

    context.execute()

    assert expired.revoked_at is None
    assert revoked.revoked_at == revoked_at
    assert context.sessions.save.await_count == 2
    (message,) = context.store.state.messages
    assert isinstance(message, AllSessionsLoggedOut)
    assert message.revoked_sessions_count == 2


def test_empty_session_list_succeeds_without_audit(
    context: LogoutAllSessionsContext,
) -> None:
    context.store.state.sessions.clear()

    context.execute()

    context.sessions.save.assert_not_awaited()
    context.outbox.add.assert_not_awaited()
    assert context.uow.commit_count == 0


def test_repeated_call_preserves_revocation_time_and_audit(
    context: LogoutAllSessionsContext,
) -> None:
    context.execute()
    context.clock.now.return_value = NOW + timedelta(minutes=1)

    context.execute()

    assert all(
        session.revoked_at == NOW for session in context.store.state.sessions.values()
    )
    assert context.uow.commit_count == 1
    assert context.sessions.save.await_count == 2
    assert len(context.store.state.messages) == 1


def test_missing_employee_is_rejected_before_loading_sessions(
    context: LogoutAllSessionsContext,
) -> None:
    context.employees.get_by_id.return_value = None

    with pytest.raises(EmployeeNotFoundError):
        context.execute()

    context.sessions.list_active_by_employee_with_lock.assert_not_awaited()
    context.sessions.save.assert_not_awaited()
    context.outbox.add.assert_not_awaited()
    assert context.uow.commit_count == 0


@pytest.mark.parametrize("failure", ["second_save", "outbox", "commit"])
def test_failure_rolls_back_all_revocations_and_audit(
    context: LogoutAllSessionsContext,
    failure: str,
) -> None:
    if failure == "second_save":
        successful_saves = 0

        async def save_then_fail(session: RefreshSession) -> None:
            nonlocal successful_saves
            if successful_saves == 1:
                raise RuntimeError("Save failed")
            context.store.state.sessions[session.id] = session
            successful_saves += 1

        context.sessions.save.side_effect = save_then_fail
    elif failure == "outbox":
        context.outbox.add.side_effect = RuntimeError("Outbox failed")
    else:
        context.uow.fail_commit = True

    with pytest.raises(RuntimeError):
        context.execute()

    assert all(
        session.revoked_at is None
        for session in context.store.state.sessions.values()
    )
    assert context.store.state.messages == []
    assert context.uow.commit_count == 0
    assert context.uow.rollback_count == 1


def test_command_from_authenticated_actor_revokes_current_session_too(
    context: LogoutAllSessionsContext,
) -> None:
    current_session = next(iter(context.store.state.sessions.values()))
    verifier = Mock(spec=AccessTokenVerifier)
    verifier.verify.return_value = AccessTokenClaims(
        employee_id=context.employee.id,
        sid=current_session.id,
        roles=context.employee.roles,
        expires_at=NOW + timedelta(minutes=10),
    )
    context.sessions.get_by_id.side_effect = (
        lambda session_id: context.store.state.sessions.get(session_id)
    )
    authenticator = AuthenticateAccessToken(
        clock=context.clock,
        uow=UnitOfWorkFake(),
        employees=context.employees,
        refresh_sessions=context.sessions,
        access_token_verifier=verifier,
    )

    async def run() -> None:
        actor = await authenticator.execute("access-token")
        await context.handler.execute(
            LogoutAllSessionsCommand(employee_id=actor.employee_id.value)
        )
        for session in context.store.state.sessions.values():
            verifier.verify.return_value = replace(
                verifier.verify.return_value,
                sid=session.id,
            )
            with pytest.raises(AuthenticationError, match="revoked"):
                await authenticator.execute("access-token")

    asyncio.run(run())


@pytest.mark.parametrize("logout_first", [True, False])
def test_concurrent_refresh_cannot_leave_existing_sessions_active(
    context: LogoutAllSessionsContext,
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
        current_hash = refresh.session.refresh_token_hash
        refresh.verifier.matches_hash.side_effect = (
            lambda token, token_hash: token == OLD_TOKEN and token_hash == current_hash
        )
        logout_request = context.handler.execute(context.command)
        refresh_request = refresh.handler.execute(RefreshAccessTokenCommand(OLD_TOKEN))
        requests = (
            (logout_request, refresh_request)
            if logout_first
            else (refresh_request, logout_request)
        )

        results = await asyncio.gather(*requests, return_exceptions=True)

        assert results[0 if logout_first else 1] is None
        refresh_result = results[1 if logout_first else 0]
        if logout_first:
            assert isinstance(refresh_result, SessionIsNotActiveError)
            refresh.access_issuer.issue.assert_not_called()
        else:
            assert isinstance(refresh_result, RefreshAccessTokenResult)
        assert all(
            session.revoked_at == NOW
            for session in context.store.state.sessions.values()
        )
        assert len(context.store.state.messages) == 1

    asyncio.run(run())
