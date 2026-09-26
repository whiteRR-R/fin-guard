import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from identity.application.commands.accept_invitation.command import (
    AcceptInvitationCommand,
)
from identity.application.commands.accept_invitation.handler import (
    AcceptInvitationHandler,
)
from identity.application.exceptions import (
    EmployeeNotFoundError,
    InvitationNotFoundError,
)
from identity.application.ports.security.invitation_token_verifier import (
    InvitationTokenClaims,
)
from identity.domain.aggregates.invitation import Invitation
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.domain.exceptions import InvitationExpiredError, InvitationRevokedError
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash
from identity.domain.value_objects.password import HashedPassword, Password
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    FixedClock,
    InvitationRepositoryFake,
    InvitationTokenVerifierStub,
    PasswordHasherStub,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
PLAIN_TOKEN = "plain-invitation-token"
VALID_PASSWORD = "valid-password-123"
PASSWORD_HASH = HashedPassword("accepted-password-hash")


def make_invitation(
    *,
    email: str = "employee@example.com",
    created_at: datetime = NOW - timedelta(hours=1),
    expires_at: datetime = NOW + timedelta(days=1),
) -> Invitation:
    return Invitation.issue(
        invitation_id=InvitationId.new(),
        invited_by=EmployeeId.new(),
        invited_email=Email(email),
        roles=(EmployeeRole.RISK_ANALYST,),
        token_hash=InvitationTokenHash("invitation-token-hash"),
        created_at=created_at,
        expires_at=expires_at,
    )


def make_handler(
    *,
    invitation: Invitation,
    additional_invitations: tuple[Invitation, ...] = (),
    invitation_exists: bool = True,
    employee_exists: bool = True,
) -> tuple[
    AcceptInvitationHandler,
    UnitOfWorkFake,
    EmployeeRepositoryFake,
    InvitationRepositoryFake,
    PasswordHasherStub,
    InvitationTokenVerifierStub,
]:
    employee = make_employee(
        invitation.invited_email.value,
        status=EmployeeStatus.INVITED,
    )
    employees = EmployeeRepositoryFake((employee,) if employee_exists else ())
    stored_invitations = (
        (invitation, *additional_invitations)
        if invitation_exists
        else additional_invitations
    )
    invitations = InvitationRepositoryFake(stored_invitations)
    password_hasher = PasswordHasherStub(
        password_is_valid=True,
        hash_result=PASSWORD_HASH,
    )
    token_verifier = InvitationTokenVerifierStub(
        InvitationTokenClaims(invitation_id=invitation.id.value)
    )
    uow = UnitOfWorkFake()
    handler = AcceptInvitationHandler(
        uow=uow,
        clock=FixedClock(NOW),
        employees=employees,
        invitations=invitations,
        password_hasher=password_hasher,
        invitation_verifier=token_verifier,
    )
    return (
        handler,
        uow,
        employees,
        invitations,
        password_hasher,
        token_verifier,
    )


def execute_accept(handler: AcceptInvitationHandler) -> None:
    asyncio.run(
        handler.execute(
            AcceptInvitationCommand(
                token=PLAIN_TOKEN,
                password=VALID_PASSWORD,
            )
        )
    )


def test_accept_invitation_saves_accepted_invitation_and_active_employee() -> None:
    invitation = make_invitation()
    handler, uow, employees, invitations, password_hasher, token_verifier = (
        make_handler(invitation=invitation)
    )

    execute_accept(handler)

    assert invitation.status is InvitationStatus.ACCEPTED
    assert invitation.accepted_at == NOW
    assert invitations.saved == [invitation]

    assert len(employees.saved) == 1
    employee = employees.saved[0]
    assert employee.email == invitation.invited_email
    assert employee.status is EmployeeStatus.ACTIVE
    assert employee.password_hash == PASSWORD_HASH

    assert password_hasher.hash_calls == [Password(VALID_PASSWORD)]
    assert token_verifier.received_tokens == [PLAIN_TOKEN]
    assert uow.commit_count == 1
    assert uow.rollback_count == 0


def test_missing_invitation_is_rejected_before_employee_lookup() -> None:
    invitation = make_invitation()
    handler, uow, employees, invitations, password_hasher, _ = make_handler(
        invitation=invitation,
        invitation_exists=False,
    )

    with pytest.raises(InvitationNotFoundError, match="Invitation not found"):
        execute_accept(handler)

    assert employees.requested_emails == []
    assert password_hasher.hash_calls == []
    assert invitations.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_missing_employee_is_rejected_before_password_hashing() -> None:
    invitation = make_invitation()
    handler, uow, employees, invitations, password_hasher, _ = make_handler(
        invitation=invitation,
        employee_exists=False,
    )

    with pytest.raises(EmployeeNotFoundError, match="Employee not found"):
        execute_accept(handler)

    assert employees.requested_emails == [invitation.invited_email]
    assert password_hasher.hash_calls == []
    assert invitations.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_expired_invitation_does_not_activate_employee() -> None:
    invitation = make_invitation(
        created_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(days=1),
    )
    handler, uow, employees, invitations, password_hasher, _ = make_handler(
        invitation=invitation
    )

    with pytest.raises(InvitationExpiredError, match="expired"):
        execute_accept(handler)

    assert invitation.status is InvitationStatus.PENDING
    assert invitations.saved == []
    assert employees.saved == []
    assert len(password_hasher.hash_calls) == 1
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_revoked_invitation_does_not_activate_employee() -> None:
    invitation = make_invitation()
    invitation.revoke(NOW - timedelta(minutes=30))
    invitation.pull_events()
    handler, uow, employees, invitations, _, _ = make_handler(
        invitation=invitation
    )

    with pytest.raises(InvitationRevokedError, match="revoked"):
        execute_accept(handler)

    assert invitation.status is InvitationStatus.REVOKED
    assert invitations.saved == []
    assert employees.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_old_token_cannot_accept_new_invitation_after_reissue() -> None:
    old_invitation = make_invitation(
        created_at=NOW - timedelta(hours=2),
    )
    old_invitation.revoke(NOW - timedelta(hours=1))
    old_invitation.pull_events()
    new_invitation = make_invitation(
        created_at=NOW - timedelta(minutes=30),
    )
    handler, uow, employees, invitations, _, token_verifier = make_handler(
        invitation=old_invitation,
        additional_invitations=(new_invitation,),
    )

    with pytest.raises(InvitationRevokedError, match="revoked"):
        execute_accept(handler)

    assert token_verifier.received_tokens == [PLAIN_TOKEN]
    assert old_invitation.status is InvitationStatus.REVOKED
    assert new_invitation.status is InvitationStatus.PENDING
    assert invitations.saved == []
    assert employees.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1
