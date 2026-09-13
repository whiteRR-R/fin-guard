import asyncio
from datetime import datetime, timedelta, timezone

from identity.application.commands.reissue_invitation.command import (
    ReissueInvitationCommand,
)
from identity.application.commands.reissue_invitation.handler import (
    ReissueInvitationHandler,
)
from identity.application.ports.security.invitation_token_issuer import (
    IssuedInvitationToken,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash
from tests.unit.application.doubles import (
    EmailSenderSpy,
    FixedClock,
    InvitationTokenIssuerStub,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee

NOW = datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)
TOKEN_EXPIRES_AT = NOW + timedelta(days=1)


class AllowInvitePolicyStub(EmployeeInvitePolicy):
    def __init__(self) -> None:
        self.checked_employees: list[EmployeeAccount] = []

    def ensure_allow(self, actor: EmployeeAccount) -> None:
        self.checked_employees.append(actor)


def make_token_issuer() -> InvitationTokenIssuerStub:
    return InvitationTokenIssuerStub(
        IssuedInvitationToken(
            plain_token="plain-reissued-invitation-token",
            token_hash=InvitationTokenHash("reissued-token-hash"),
            expires_at=TOKEN_EXPIRES_AT,
        )
    )


def test_reinvite_employee_creates_employee_and_invitation_atomically():
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    
    uow = UnitOfWorkFake(active_at=NOW, employees=(admin,))
    policy = AllowInvitePolicyStub()
    token_issuer = make_token_issuer()
    email_sendler = EmailSenderSpy()
    handler = ReissueInvitationHandler(
        uow=uow,
        clock=FixedClock(NOW),
        invitation_policy=policy,
        email_sender=email_sendler,
        invitation_token_issuer=token_issuer,
    )

    result = asyncio.run(
        handler.execute(
            ReissueInvitationCommand(
                inviter_id=admin.id.value,
                employee_email=" AuDitor@example.com    ",
            )
        )
    )

    assert policy.checked_employees == [admin]
    assert len(uow.employees.added) == 1

    employee = uow.employees.added[0]

    assert employee.id.value == result.employee_id
    assert employee.email.value == "auditor@example.com"
    assert employee.roles == frozenset(
        {
            EmployeeRole.AUDITOR,
        }
    )
    assert employee.status == EmployeeStatus.INVITED

    assert len(uow.invitations.added) == 1

    invitation = uow.invitations.added[0]

    assert invitation.id.value == result.invitation_id
    assert invitation.invited_by == admin.id
    assert invitation.invited_email == employee.email
    assert invitation.roles == employee.roles
    assert invitation.status is InvitationStatus.PENDING
    assert invitation.token_hash == InvitationTokenHash("reissued-token-hash")
    assert invitation.created_at == NOW
    assert invitation.expires_at == TOKEN_EXPIRES_AT

    assert token_issuer.calls == [
        (invitation.id, admin.id, employee.id, NOW)
    ]
    assert email_sendler.sent_messages == [
        (employee.email, "plain-reissued-invitation-token")
    ]
    assert uow.commit_count == 1
    assert uow.rollback_count == 0
