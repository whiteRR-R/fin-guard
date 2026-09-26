import asyncio
from datetime import datetime, timedelta, timezone

from identity.application.commands.reissue_invitation.command import (
    ReissueInvitationCommand,
)
from identity.application.commands.reissue_invitation.handler import (
    ReissueInvitationHandler,
)
from identity.application.messages.invitation_email_requested import (
    InvitationEmailRequested,
)
from identity.application.ports.security.invitation_token_issuer import (
    IssuedInvitationToken,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.invitation import Invitation
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    FixedClock,
    InvitationRepositoryFake,
    InvitationTokenIssuerStub,
    OutboxRepositoryFake,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee

NOW = datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)
TOKEN_EXPIRES_AT = NOW + timedelta(days=1)


class AllowInvitePolicyStub(EmployeeInvitePolicy):
    def __init__(self) -> None:
        self.checked_employees: list[EmployeeAccount] = []

    def ensure_allowed(self, actor: EmployeeAccount) -> None:
        self.checked_employees.append(actor)


def make_token_issuer() -> InvitationTokenIssuerStub:
    return InvitationTokenIssuerStub(
        IssuedInvitationToken(
            plain_token="plain-reissued-invitation-token",
            token_hash=InvitationTokenHash("reissued-token-hash"),
            expires_at=TOKEN_EXPIRES_AT,
        )
    )


def test_reissue_expired_invitation_saves_new_invitation_and_outbox() -> None:
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    invited_employee = make_employee(
        "auditor@example.com",
        roles=(EmployeeRole.AUDITOR,),
        status=EmployeeStatus.INVITED,
    )
    expired_invitation = Invitation.issue(
        invitation_id=InvitationId.new(),
        invited_by=admin.id,
        invited_email=Email("auditor@example.com"),
        roles=(EmployeeRole.AUDITOR,),
        token_hash=InvitationTokenHash("expired-token-hash"),
        created_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(days=1),
    )
    employees = EmployeeRepositoryFake((admin, invited_employee))
    invitations = InvitationRepositoryFake((expired_invitation,))
    outbox = OutboxRepositoryFake()
    uow = UnitOfWorkFake()
    policy = AllowInvitePolicyStub()
    token_issuer = make_token_issuer()
    handler = ReissueInvitationHandler(
        uow=uow,
        outbox=outbox,
        employees=employees,
        invitations=invitations,
        clock=FixedClock(NOW),
        invitation_policy=policy,
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
    assert employees.added == []
    assert invited_employee.id.value == result.employee_id
    assert invited_employee.status is EmployeeStatus.INVITED

    assert len(invitations.added) == 1

    invitation = invitations.added[0]

    assert invitation.id.value == result.invitation_id
    assert invitation.invited_by == admin.id
    assert invitation.invited_email == invited_employee.email
    assert invitation.roles == invited_employee.roles
    assert invitation.status is InvitationStatus.PENDING
    assert invitation.token_hash == InvitationTokenHash("reissued-token-hash")
    assert invitation.created_at == NOW
    assert invitation.expires_at == TOKEN_EXPIRES_AT

    assert token_issuer.calls == [(invitation.id, NOW)]
    assert len(outbox.added) == 1
    message = outbox.added[0]
    assert isinstance(message, InvitationEmailRequested)
    assert message.invitation_id == invitation.id.value
    assert message.recipient_email == invited_employee.email.value
    assert not hasattr(message, "invitation_token")
    assert "plain-reissued-invitation-token" not in repr(message)
    assert uow.commit_count == 1
    assert uow.rollback_count == 0


def test_reissue_pending_invitation_revokes_previous_invitation() -> None:
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    invited_employee = make_employee(
        "auditor@example.com",
        roles=(EmployeeRole.AUDITOR,),
        status=EmployeeStatus.INVITED,
    )
    current_invitation = Invitation.issue(
        invitation_id=InvitationId.new(),
        invited_by=admin.id,
        invited_email=invited_employee.email,
        roles=invited_employee.roles,
        token_hash=InvitationTokenHash("current-token-hash"),
        created_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
    )
    employees = EmployeeRepositoryFake((admin, invited_employee))
    invitations = InvitationRepositoryFake((current_invitation,))
    outbox = OutboxRepositoryFake()
    uow = UnitOfWorkFake()
    handler = ReissueInvitationHandler(
        uow=uow,
        clock=FixedClock(NOW),
        outbox=outbox,
        employees=employees,
        invitations=invitations,
        invitation_policy=AllowInvitePolicyStub(),
        invitation_token_issuer=make_token_issuer(),
    )

    asyncio.run(
        handler.execute(
            ReissueInvitationCommand(
                inviter_id=admin.id.value,
                employee_email=invited_employee.email.value,
            )
        )
    )

    assert current_invitation.status is InvitationStatus.REVOKED
    assert current_invitation.revoked_at == NOW
    assert invitations.saved == [current_invitation]
    assert len(invitations.added) == 1
    assert len(outbox.added) == 1
    assert uow.commit_count == 1
    assert uow.rollback_count == 0
