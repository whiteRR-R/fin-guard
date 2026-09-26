from datetime import timedelta

import pytest

from identity.application.commands.refresh_access_token.command import (
    RefreshAccessTokenCommand,
)
from identity.application.commands.refresh_access_token.result import (
    RefreshAccessTokenResult,
)
from identity.application.exceptions import (
    EmployeeNotActiveError,
    EmployeeNotFoundError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
    SessionIsNotActiveError,
    SessionNotFoundError,
)
from identity.application.messages.refresh_token_reuse_detected import (
    RefreshTokenReuseDetected,
)
from identity.application.ports.security.refresh_token_issuer import IssuedRefreshToken
from identity.application.ports.security.refresh_token_verifier import RefreshTokenClaims
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.refresh_session import RefreshSessionId
from tests.unit.application.refresh_access_token_support import (
    NEW_HASH,
    NEW_TOKEN,
    NOW,
    OLD_HASH,
    OLD_TOKEN,
    RefreshContext,
    make_context,
)


@pytest.fixture
def context() -> RefreshContext:
    return make_context()


def test_success_rotates_existing_session_and_commits_history(
    context: RefreshContext,
) -> None:
    expires_at = context.session.expires_at

    result = context.execute()

    assert result == RefreshAccessTokenResult("access-secret", NEW_TOKEN)
    assert context.session.refresh_token_hash == NEW_HASH
    assert context.session.expires_at == expires_at
    assert context.store.state.history[context.session_id] == [OLD_HASH]
    assert context.uow.commit_count == 1
    assert context.uow.rollback_count == 0
    context.sessions.get_by_id_with_lock.assert_awaited_once_with(context.session_id)
    context.sessions.get_by_id.assert_not_awaited()
    context.access_issuer.issue.assert_called_once_with(
        employee_id=context.employee.id,
        session_id=context.session_id,
        roles=context.employee.roles,
        issued_at=NOW,
    )


def test_unknown_token_is_rejected_without_revoking_session(
    context: RefreshContext,
) -> None:
    with pytest.raises(InvalidRefreshTokenError):
        context.execute("unknown-token")

    context.assert_no_issue_or_commit()
    assert context.session.is_active(NOW)


def test_missing_session_is_rejected(context: RefreshContext) -> None:
    context.store.state.sessions.clear()

    with pytest.raises(SessionNotFoundError):
        context.execute()

    context.assert_no_issue_or_commit()


def test_expired_session_is_rejected() -> None:
    context = make_context(expires_at=NOW)

    with pytest.raises(SessionIsNotActiveError):
        context.execute()

    context.assert_no_issue_or_commit()


def test_revoked_session_is_rejected(context: RefreshContext) -> None:
    context.session.revoke(NOW)

    with pytest.raises(SessionIsNotActiveError):
        context.execute()

    context.assert_no_issue_or_commit()


def test_session_cannot_be_used_before_creation(context: RefreshContext) -> None:
    context.clock.current_time = NOW - timedelta(hours=2)

    with pytest.raises(SessionIsNotActiveError):
        context.execute()

    context.assert_no_issue_or_commit()


@pytest.mark.parametrize("status", [EmployeeStatus.BLOCKED, EmployeeStatus.INVITED])
def test_inactive_employee_cannot_refresh(status: EmployeeStatus) -> None:
    context = make_context(status=status)

    with pytest.raises(EmployeeNotActiveError):
        context.execute()

    context.assert_no_issue_or_commit()


def test_missing_employee_cannot_refresh(context: RefreshContext) -> None:
    context.employees.get_by_id.return_value = None

    with pytest.raises(EmployeeNotFoundError):
        context.execute()

    context.assert_no_issue_or_commit()


def test_expired_token_is_rejected_even_when_session_is_active(
    context: RefreshContext,
) -> None:
    context.verifier.verify.return_value = RefreshTokenClaims(
        session_id=context.session_id,
        expires_at=NOW,
    )

    with pytest.raises(InvalidRefreshTokenError, match="expired"):
        context.execute()

    context.assert_no_issue_or_commit()


def test_expiry_is_checked_after_waiting_for_session_lock(
    context: RefreshContext,
) -> None:
    async def get_after_expiry(session_id: RefreshSessionId) -> RefreshSession:
        await context.uow.lock_session()
        context.clock.current_time = NOW + timedelta(days=2)
        return context.store.state.sessions[session_id]

    context.sessions.get_by_id_with_lock.side_effect = get_after_expiry

    with pytest.raises(InvalidRefreshTokenError, match="expired"):
        context.execute()

    context.assert_no_issue_or_commit()


def test_invalid_signature_is_rejected_before_repository_access(
    context: RefreshContext,
) -> None:
    context.verifier.verify.side_effect = InvalidRefreshTokenError("Invalid signature")

    with pytest.raises(InvalidRefreshTokenError):
        context.execute()

    context.sessions.get_by_id_with_lock.assert_not_awaited()
    context.assert_no_issue_or_commit()


def test_old_token_reuse_commits_revocation_and_audit_before_raising(
    context: RefreshContext,
) -> None:
    context.execute()

    with pytest.raises(RefreshTokenReuseError):
        context.execute()

    assert context.session.revoked_at == NOW
    assert context.uow.commit_count == 2
    assert context.uow.rollback_count == 0
    context.access_issuer.issue.assert_called_once()
    context.refresh_issuer.issue.assert_called_once()

    message, = context.store.state.messages
    assert isinstance(message, RefreshTokenReuseDetected)
    assert message.session_id == context.session_id.value
    assert message.employee_id == context.employee.id.value
    assert message.created_at == NOW
    assert message.version == 1
    assert OLD_TOKEN not in repr(message)
    assert OLD_HASH.value not in repr(message)

    with pytest.raises(SessionIsNotActiveError):
        context.execute(NEW_TOKEN)


@pytest.mark.parametrize("already_used", [False, True])
def test_issuer_cannot_reissue_current_or_historical_token(
    context: RefreshContext,
    already_used: bool,
) -> None:
    if already_used:
        context.store.state.history[context.session_id] = [NEW_HASH]
    else:
        context.refresh_issuer.issue.return_value = IssuedRefreshToken(
            plain_token=OLD_TOKEN,
            token_hash=OLD_HASH,
        )

    with pytest.raises(InvalidRefreshTokenError, match="issuer reused"):
        context.execute()

    assert context.session.refresh_token_hash == OLD_HASH
    assert context.uow.commit_count == 0
    context.access_issuer.issue.assert_not_called()


def test_command_and_result_repr_hide_tokens() -> None:
    command = RefreshAccessTokenCommand(OLD_TOKEN)
    result = RefreshAccessTokenResult("access-secret", NEW_TOKEN)

    assert OLD_TOKEN not in repr(command)
    assert NEW_TOKEN not in repr(result)
    assert "access-secret" not in repr(result)
