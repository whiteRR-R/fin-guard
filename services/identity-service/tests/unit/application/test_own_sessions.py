import asyncio
from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from identity.application.authentication.authenticate_access_token import (
    AuthenticateAccessToken,
)
from identity.application.commands.refresh_access_token.command import (
    RefreshAccessTokenCommand,
)
from identity.application.commands.refresh_access_token.result import (
    RefreshAccessTokenResult,
)
from identity.application.commands.revoke_own_session.command import (
    RevokeOwnSessionCommand,
)
from identity.application.exceptions import (
    AccessDeniedError,
    SessionIsNotActiveError,
    SessionNotFoundError,
)
from identity.application.messages.session_revoked import SessionRevoked
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.security.access_token_verifier import (
    AccessTokenClaims,
    AccessTokenVerifier,
)
from identity.application.queries.list_own_sessions.query import ListOwnSessionsQuery
from identity.domain.value_objects.refresh_session import RefreshSessionId
from tests.unit.application.doubles import UnitOfWorkFake
from tests.unit.application.factories import make_refresh_session
from tests.unit.application.own_sessions_support import (
    NOW,
    OwnSessionsContext,
    make_context,
)
from tests.unit.application.refresh_access_token_support import (
    OLD_TOKEN,
    make_context as make_refresh_context,
)


@pytest.fixture
def context() -> OwnSessionsContext:
    return make_context()


def test_list_returns_only_own_sessions_with_current_first(
    context: OwnSessionsContext,
) -> None:
    result = context.list_sessions()

    assert [session.session_id for session in result.sessions] == [
        context.current_session.id.value,
        context.target_session.id.value,
        context.other_session.id.value,
    ]
    assert [session.is_current for session in result.sessions] == [True, False, False]
    assert result.sessions[0].created_at == context.current_session.created_at
    assert result.sessions[0].expires_at == context.current_session.expires_at
    assert "refresh-token-hash" not in repr(result)
    assert not hasattr(result.sessions[0], "refresh_token_hash")
    context.sessions.list_active_by_employee.assert_awaited_once_with(context.employee.id)
    context.sessions.get_by_id_with_lock.assert_not_awaited()
    context.sessions.save.assert_not_awaited()
    context.outbox.add.assert_not_awaited()
    assert context.list_uow.commit_count == 0
    assert context.target_session.is_active(NOW)


def test_list_filters_expired_revoked_and_foreign_records(
    context: OwnSessionsContext,
) -> None:
    expired = make_refresh_session(context.employee.id, now=NOW - timedelta(hours=1))
    context.target_session.revoke(NOW)
    context.sessions.list_active_by_employee.side_effect = None
    context.sessions.list_active_by_employee.return_value = [
        expired,
        context.target_session,
        context.foreign_session,
        context.current_session,
    ]

    result = context.list_sessions()

    assert [session.session_id for session in result.sessions] == [
        context.current_session.id.value
    ]
    assert context.list_uow.commit_count == 0


def test_list_returns_empty_tuple_when_no_active_sessions_remain(
    context: OwnSessionsContext,
) -> None:
    for session in context.store.state.sessions.values():
        if session.employee_id == context.employee.id:
            session.revoke(NOW)

    assert context.list_sessions().sessions == ()
    assert context.list_uow.commit_count == 0


def test_revoke_removes_selected_session_from_list_and_records_audit(
    context: OwnSessionsContext,
) -> None:
    context.revoke()

    assert context.target_session.revoked_at == NOW
    assert context.current_session.is_active(NOW)
    assert context.other_session.is_active(NOW)
    assert context.foreign_session.is_active(NOW)
    assert [session.session_id for session in context.list_sessions().sessions] == [
        context.current_session.id.value,
        context.other_session.id.value,
    ]
    context.sessions.get_by_id_with_lock.assert_awaited_once_with(context.target_session.id)
    assert context.revoke_uow.commit_count == 1
    message, = context.store.state.messages
    assert isinstance(message, SessionRevoked)
    assert message.session_id == context.target_session.id.value
    assert message.employee_id == context.employee.id.value
    assert message.created_at == NOW
    assert message.version == 1


def test_current_session_can_be_revoked(context: OwnSessionsContext) -> None:
    context.revoke(
        replace(context.command, target_session_id=context.current_session.id.value)
    )

    assert context.current_session.revoked_at == NOW
    assert context.target_session.is_active(NOW)
    assert all(not session.is_current for session in context.list_sessions().sessions)


@pytest.mark.parametrize("already_revoked", [False, True])
def test_foreign_session_is_rejected_before_any_change(
    context: OwnSessionsContext,
    already_revoked: bool,
) -> None:
    if already_revoked:
        context.foreign_session.revoke(NOW - timedelta(minutes=1))
    previous_revocation = context.foreign_session.revoked_at
    command = replace(
        context.command,
        target_session_id=context.foreign_session.id.value,
    )

    with pytest.raises(AccessDeniedError):
        context.revoke(command)

    saved = context.store.state.sessions[context.foreign_session.id]
    assert saved.revoked_at == previous_revocation
    context.sessions.save.assert_not_awaited()
    context.outbox.add.assert_not_awaited()
    assert context.revoke_uow.commit_count == 0


def test_missing_session_is_rejected(context: OwnSessionsContext) -> None:
    command = replace(context.command, target_session_id=RefreshSessionId.new().value)

    with pytest.raises(SessionNotFoundError):
        context.revoke(command)

    context.sessions.save.assert_not_awaited()
    context.outbox.add.assert_not_awaited()
    assert context.revoke_uow.commit_count == 0


def test_repeated_revoke_preserves_timestamp_and_audit(
    context: OwnSessionsContext,
) -> None:
    context.revoke()
    context.clock.now.return_value = NOW + timedelta(minutes=1)

    context.revoke()

    assert context.store.state.sessions[context.target_session.id].revoked_at == NOW
    assert context.revoke_uow.commit_count == 1
    context.sessions.save.assert_awaited_once()
    assert len(context.store.state.messages) == 1


@pytest.mark.parametrize("failure", ["save", "outbox", "commit"])
def test_revoke_failure_rolls_back_session_and_audit(
    context: OwnSessionsContext,
    failure: str,
) -> None:
    if failure == "save":
        context.sessions.save.side_effect = RuntimeError("Save failed")
    elif failure == "outbox":
        context.outbox.add.side_effect = RuntimeError("Outbox failed")
    else:
        context.revoke_uow.fail_commit = True

    with pytest.raises(RuntimeError):
        context.revoke()

    assert context.store.state.sessions[context.target_session.id].is_active(NOW)
    assert context.store.state.messages == []
    assert context.revoke_uow.commit_count == 0
    assert context.revoke_uow.rollback_count == 1


def test_authenticated_actor_can_list_and_revoke_selected_session(
    context: OwnSessionsContext,
) -> None:
    employees = AsyncMock(spec=EmployeeRepository)
    employees.get_by_id.return_value = context.employee
    verifier = Mock(spec=AccessTokenVerifier)
    verifier.verify.return_value = AccessTokenClaims(
        employee_id=context.employee.id,
        sid=context.current_session.id,
        roles=context.employee.roles,
        expires_at=NOW + timedelta(minutes=10),
    )
    authenticator = AuthenticateAccessToken(
        clock=context.clock,
        uow=UnitOfWorkFake(),
        employees=employees,
        refresh_sessions=context.sessions,
        access_token_verifier=verifier,
    )

    async def run() -> None:
        actor = await authenticator.execute("access-token")
        result = await context.list_handler.execute(
            ListOwnSessionsQuery(
                employee_id=actor.employee_id.value,
                current_session_id=actor.session_id.value,
            )
        )
        selected = next(session for session in result.sessions if not session.is_current)
        await context.revoke_handler.execute(
            RevokeOwnSessionCommand(
                employee_id=actor.employee_id.value,
                target_session_id=selected.session_id,
            )
        )
        selected_session = context.store.state.sessions[
            RefreshSessionId(selected.session_id)
        ]
        assert selected_session.revoked_at == NOW
        assert context.current_session.is_active(NOW)

    asyncio.run(run())


@pytest.mark.parametrize("revoke_first", [True, False])
def test_concurrent_refresh_cannot_reactivate_selected_session(
    context: OwnSessionsContext,
    revoke_first: bool,
) -> None:
    async def run() -> None:
        refresh = make_refresh_context(employee=context.employee, store=context.store)
        refresh.clock.current_time = NOW
        refresh.verifier.verify.return_value = replace(
            refresh.verifier.verify.return_value,
            session_id=context.target_session.id,
            expires_at=NOW + timedelta(hours=1),
        )
        initial_hash = context.target_session.refresh_token_hash
        refresh.verifier.matches_hash.side_effect = (
            lambda token, token_hash: token == OLD_TOKEN and token_hash == initial_hash
        )
        revoke_request = context.revoke_handler.execute(context.command)
        refresh_request = refresh.handler.execute(RefreshAccessTokenCommand(OLD_TOKEN))
        requests = (
            (revoke_request, refresh_request)
            if revoke_first
            else (refresh_request, revoke_request)
        )

        results = await asyncio.gather(*requests, return_exceptions=True)

        assert results[0 if revoke_first else 1] is None
        refresh_result = results[1 if revoke_first else 0]
        if revoke_first:
            assert isinstance(refresh_result, SessionIsNotActiveError)
            refresh.access_issuer.issue.assert_not_called()
        else:
            assert isinstance(refresh_result, RefreshAccessTokenResult)
        assert context.target_session.revoked_at == NOW
        assert context.current_session.is_active(NOW)
        assert len(context.store.state.messages) == 1

    asyncio.run(run())
