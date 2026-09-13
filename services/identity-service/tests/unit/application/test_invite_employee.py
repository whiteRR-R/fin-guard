import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from identity.application.commands.invite_employee.command import InviteEmployeeCommand
from identity.application.commands.invite_employee.handler import InviteEmployeeHandler
from identity.application.exceptions import (
    AuthenticationError,
    EmployeeAlreadyInvitedError,
)
from identity.application.ports.security.invitation_token_issuer import (
    IssuedInvitationToken,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash
from tests.unit.application.doubles import (
    EmailSenderSpy,
    FixedClock,
    InvitationTokenIssuerStub,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
TOKEN_EXPIRES_AT = NOW + timedelta(days=1)


class AllowInvitePolicyStub(EmployeeInvitePolicy):
    def __init__(self) -> None:
        self.checked_employees: list[EmployeeAccount] = []

    def ensure_allowed(self, actor: EmployeeAccount) -> None:
        self.checked_employees.append(actor)


def make_token_issuer() -> InvitationTokenIssuerStub:
    return InvitationTokenIssuerStub(
        IssuedInvitationToken(
            plain_token="plain-invitation-token",
            token_hash=InvitationTokenHash("invitation-token-hash"),
            expires_at=TOKEN_EXPIRES_AT,
        )
    )


def test_invite_employee_creates_employee_and_invitation_atomically() -> None:
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    uow = UnitOfWorkFake(active_at=NOW, employees=(admin,))
    policy = AllowInvitePolicyStub()
    token_issuer = make_token_issuer()
    email_sender = EmailSenderSpy()
    handler = InviteEmployeeHandler(
        uow=uow,
        clock=FixedClock(NOW),
        invite_policy=policy,
        email_sendler=email_sender,
        invitation_token_issuer=token_issuer,
    )

    result = asyncio.run(
        handler.execute(
            InviteEmployeeCommand(
                actor_id=admin.id.value,
                employee_email="  ANALYST@example.com  ",
                employee_roles=(EmployeeRole.RISK_ANALYST,),
            )
        )
    )

    assert policy.checked_employees == [admin]
    assert len(uow.employees.added) == 1
    employee = uow.employees.added[0]
    assert employee.id.value == result.employee_id
    assert employee.email.value == "analyst@example.com"
    assert employee.roles == frozenset({EmployeeRole.RISK_ANALYST})
    assert employee.status is EmployeeStatus.INVITED

    assert len(uow.invitations.added) == 1
    invitation = uow.invitations.added[0]
    assert invitation.id.value == result.invitation_id
    assert invitation.invited_by == admin.id
    assert invitation.invited_email == employee.email
    assert invitation.roles == employee.roles
    assert invitation.status is InvitationStatus.PENDING
    assert invitation.token_hash == InvitationTokenHash("invitation-token-hash")
    assert invitation.created_at == NOW
    assert invitation.expires_at == TOKEN_EXPIRES_AT

    assert token_issuer.calls == [
        (invitation.id, admin.id, employee.email, NOW)
    ]
    assert email_sender.sent_messages == [
        (employee.email, "plain-invitation-token")
    ]
    assert uow.commit_count == 1
    assert uow.rollback_count == 0


def test_existing_employee_is_rejected_before_token_is_issued() -> None:
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    existing_employee = make_employee(
        "analyst@example.com",
        status=EmployeeStatus.INVITED,
    )
    uow = UnitOfWorkFake(
        active_at=NOW,
        employees=(admin, existing_employee),
    )
    token_issuer = make_token_issuer()
    email_sender = EmailSenderSpy()
    handler = InviteEmployeeHandler(
        uow=uow,
        clock=FixedClock(NOW),
        invite_policy=AllowInvitePolicyStub(),
        email_sendler=email_sender,
        invitation_token_issuer=token_issuer,
    )

    with pytest.raises(EmployeeAlreadyInvitedError, match="already invited"):
        asyncio.run(
            handler.execute(
                InviteEmployeeCommand(
                    actor_id=admin.id.value,
                    employee_email="ANALYST@example.com",
                    employee_roles=(EmployeeRole.RISK_ANALYST,),
                )
            )
        )

    assert token_issuer.calls == []
    assert email_sender.sent_messages == []
    assert uow.employees.added == []
    assert uow.invitations.added == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_missing_inviter_is_rejected_before_email_lookup() -> None:
    missing_inviter_id = EmployeeId.new()
    uow = UnitOfWorkFake(active_at=NOW)
    policy = AllowInvitePolicyStub()
    token_issuer = make_token_issuer()
    email_sender = EmailSenderSpy()
    handler = InviteEmployeeHandler(
        uow=uow,
        clock=FixedClock(NOW),
        invite_policy=policy,
        email_sendler=email_sender,
        invitation_token_issuer=token_issuer,
    )

    with pytest.raises(AuthenticationError, match="Inviter not found"):
        asyncio.run(
            handler.execute(
                InviteEmployeeCommand(
                    actor_id=missing_inviter_id.value,
                    employee_email="analyst@example.com",
                    employee_roles=(EmployeeRole.RISK_ANALYST,),
                )
            )
        )

    assert policy.checked_employees == []
    assert uow.employees.requested_emails == []
    assert token_issuer.calls == []
    assert email_sender.sent_messages == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1
