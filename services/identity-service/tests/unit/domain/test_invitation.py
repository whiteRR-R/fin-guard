from datetime import datetime, timedelta, timezone

import pytest

from identity.domain.aggregates.invitation import Invitation
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import InvitationStatus
from identity.domain.events.invitation import InvitationAccepted, InvitationRevoked
from identity.domain.exceptions import (
    InvalidInvitationPeriodError,
    InvalidInvitationStatusError,
    InvitationAlreadyAcceptedError,
    InvitationExpiredError,
    InvitationRevokedError,
    InvitationTokenHashValidationError,
)
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def issue_invitation(
    *,
    created_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(days=1),
) -> Invitation:
    return Invitation.issue(
        invitation_id=InvitationId.new(),
        invited_email=Email("employee@example.com"),
        roles={EmployeeRole.RISK_ANALYST},
        invited_by=EmployeeId.new(),
        token_hash=InvitationTokenHash("invitation-token-hash"),
        created_at=created_at,
        expires_at=expires_at,
    )


def test_pending_invitation_can_be_accepted() -> None:
    invitation = issue_invitation()
    accepted_at = NOW + timedelta(hours=1)

    invitation.accept(accepted_at)

    assert invitation.status is InvitationStatus.ACCEPTED
    assert invitation.accepted_at == accepted_at
    events = invitation.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], InvitationAccepted)
    assert events[0].invitation_id == invitation.id


def test_accepted_invitation_cannot_be_accepted_again() -> None:
    invitation = issue_invitation()
    invitation.accept(NOW + timedelta(hours=1))
    invitation.pull_events()

    with pytest.raises(InvitationAlreadyAcceptedError):
        invitation.accept(NOW + timedelta(hours=2))

    assert invitation.status is InvitationStatus.ACCEPTED
    assert invitation.pull_events() == ()


def test_issue_creates_pending_invitation_with_immutable_roles() -> None:
    roles = {EmployeeRole.RISK_ANALYST}
    invitation = Invitation.issue(
        invitation_id=InvitationId.new(),
        invited_email=Email("employee@example.com"),
        roles=roles,
        invited_by=EmployeeId.new(),
        token_hash=InvitationTokenHash("invitation-token-hash"),
        created_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )

    roles.clear()

    assert invitation.status is InvitationStatus.PENDING
    assert invitation.roles == frozenset({EmployeeRole.RISK_ANALYST})
    assert invitation.accepted_at is None
    assert invitation.revoked_at is None


def test_revoked_invitation_cannot_be_accepted() -> None:
    invitation = issue_invitation()
    invitation.revoke(NOW + timedelta(hours=1))

    with pytest.raises(InvitationRevokedError):
        invitation.accept(NOW + timedelta(hours=2))


def test_accepted_invitation_cannot_be_revoked() -> None:
    invitation = issue_invitation()
    invitation.accept(NOW + timedelta(hours=1))

    with pytest.raises(InvitationAlreadyAcceptedError):
        invitation.revoke(NOW + timedelta(hours=2))


def test_invitation_cannot_be_revoked_twice() -> None:
    invitation = issue_invitation()
    invitation.revoke(NOW + timedelta(hours=1))

    with pytest.raises(InvitationRevokedError):
        invitation.revoke(NOW + timedelta(hours=2))


def test_revoke_records_time_status_and_event() -> None:
    invitation = issue_invitation()
    revoked_at = NOW + timedelta(hours=1)

    invitation.revoke(revoked_at)

    assert invitation.status is InvitationStatus.REVOKED
    assert invitation.revoked_at == revoked_at
    events = invitation.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], InvitationRevoked)
    assert events[0].invitation_id == invitation.id


@pytest.mark.parametrize(
    "accepted_at",
    [NOW + timedelta(days=1), NOW + timedelta(days=1, seconds=1)],
)
def test_expired_invitation_cannot_be_accepted(accepted_at: datetime) -> None:
    invitation = issue_invitation()

    with pytest.raises(InvitationExpiredError):
        invitation.accept(accepted_at)

    assert invitation.status is InvitationStatus.PENDING
    assert invitation.accepted_at is None
    assert invitation.pull_events() == ()


@pytest.mark.parametrize(
    "expires_at",
    [NOW, NOW - timedelta(seconds=1)],
)
def test_issue_rejects_non_future_expiration(expires_at: datetime) -> None:
    with pytest.raises(InvalidInvitationPeriodError):
        issue_invitation(expires_at=expires_at)


def test_empty_token_hash_is_rejected() -> None:
    with pytest.raises(InvitationTokenHashValidationError):
        InvitationTokenHash("")


def test_token_hash_is_not_exposed_in_repr() -> None:
    token_hash = InvitationTokenHash("sensitive-hash")

    assert "sensitive-hash" not in repr(token_hash)


def test_restore_rejects_pending_invitation_with_accepted_time() -> None:
    with pytest.raises(InvalidInvitationStatusError):
        Invitation.restore(
            invitation_id=InvitationId.new(),
            invited_by=EmployeeId.new(),
            invited_email=Email("employee@example.com"),
            roles=(EmployeeRole.AUDITOR,),
            status=InvitationStatus.PENDING,
            token_hash=InvitationTokenHash("invitation-token-hash"),
            created_at=NOW,
            expires_at=NOW + timedelta(days=1),
            accepted_at=NOW + timedelta(hours=1),
            revoked_at=None,
        )


def test_operation_time_cannot_be_before_creation() -> None:
    invitation = issue_invitation()

    with pytest.raises(InvalidInvitationPeriodError):
        invitation.accept(NOW - timedelta(seconds=1))
