import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from identity.application.commands.accept_invitation.command import (
    AcceptInvitationCommand,
)
from identity.application.commands.accept_invitation.handler import (
    AcceptInvitationHandler,
)
from identity.application.commands.invite_employee.command import InviteEmployeeCommand
from identity.application.commands.invite_employee.handler import InviteEmployeeHandler
from identity.application.email_delivery.deliver_invitation_email import (
    DeliverInvitationEmail,
)
from identity.application.exceptions import (
    InvalidInvitationTokenError,
    InvitationDeliveryError,
)
from identity.application.messages.invitation_email_requested import (
    InvitationEmailRequested,
)
from identity.domain.aggregates.invitation import Invitation
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.invitation_id import InvitationId
from identity.infrastructure.security.hmac_invitation_tokens import HmacInvitationTokens
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    FixedClock,
    InvitationRepositoryFake,
    OutboxRepositoryFake,
    PasswordHasherStub,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


class EmailSenderFake:
    def __init__(self) -> None:
        self.sent: list[tuple[Email, str]] = []

    async def send(self, email: Email, plain_token: str) -> None:
        self.sent.append((email, plain_token))


def test_invitation_is_delivered_and_accepted_without_storing_plain_token() -> None:
    tokens = HmacInvitationTokens(
        b"test-signing-key-with-at-least-32-bytes", timedelta(days=1)
    )
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    employees = EmployeeRepositoryFake((admin,))
    invitations = InvitationRepositoryFake()
    outbox = OutboxRepositoryFake()
    clock = FixedClock(NOW)

    invite = InviteEmployeeHandler(
        uow=UnitOfWorkFake(),
        clock=clock,
        outbox=outbox,
        employees=employees,
        invitations=invitations,
        invite_policy=EmployeeInvitePolicy(),
        invitation_token_issuer=tokens,
    )
    asyncio.run(
        invite.execute(
            InviteEmployeeCommand(
                inviter_id=admin.id.value,
                employee_email="employee@example.com",
                employee_roles=(EmployeeRole.AUDITOR,),
            )
        )
    )

    message = outbox.added[0]
    assert isinstance(message, InvitationEmailRequested)
    invitation = invitations.added[0]
    sender = EmailSenderFake()
    deliver = DeliverInvitationEmail(
        uow=UnitOfWorkFake(),
        clock=clock,
        invitations=invitations,
        token_issuer=tokens,
        token_verifier=tokens,
        email_sender=sender,
    )
    asyncio.run(deliver.execute(message))

    assert len(sender.sent) == 1
    recipient, plain_token = sender.sent[0]
    assert recipient == Email("employee@example.com")
    assert plain_token == tokens.derive_token(invitation.id)
    assert tokens.matches_hash(plain_token, invitation.token_hash)
    assert plain_token not in str(asdict(message))
    assert plain_token not in repr(message)

    accept = AcceptInvitationHandler(
        uow=UnitOfWorkFake(),
        clock=clock,
        employees=employees,
        invitations=invitations,
        password_hasher=PasswordHasherStub(password_is_valid=True),
        invitation_verifier=tokens,
    )
    asyncio.run(
        accept.execute(
            AcceptInvitationCommand(token=plain_token, password="valid-password-123")
        )
    )

    employee = asyncio.run(employees.get_by_email(recipient))
    assert employee is not None
    assert employee.status is EmployeeStatus.ACTIVE
    assert invitation.status is InvitationStatus.ACCEPTED

    with pytest.raises(InvalidInvitationTokenError):
        tokens.parse_verified(plain_token[:-1] + ("A" if plain_token[-1] != "A" else "B"))


def test_delivery_skips_revoked_invitation() -> None:
    tokens = HmacInvitationTokens(
        b"test-signing-key-with-at-least-32-bytes", timedelta(days=1)
    )
    invitation_id = InvitationId.new()
    invited_by = make_employee("admin@example.com").id
    issued = tokens.issue(
        invitation_id=invitation_id,
        issued_at=NOW,
    )
    invitation = Invitation.issue(
        invitation_id=invitation_id,
        invited_by=invited_by,
        invited_email=Email("employee@example.com"),
        roles=(EmployeeRole.AUDITOR,),
        token_hash=issued.token_hash,
        created_at=NOW,
        expires_at=issued.expires_at,
    )
    invitation.revoke(NOW + timedelta(minutes=1))
    sender = EmailSenderFake()
    deliver = DeliverInvitationEmail(
        uow=UnitOfWorkFake(),
        clock=FixedClock(NOW + timedelta(minutes=2)),
        invitations=InvitationRepositoryFake((invitation,)),
        token_issuer=tokens,
        token_verifier=tokens,
        email_sender=sender,
    )

    asyncio.run(
        deliver.execute(
            InvitationEmailRequested(
                invitation_id=invitation.id.value,
                recipient_email=invitation.invited_email.value,
            )
        )
    )
    assert sender.sent == []


def test_delivery_refuses_token_signed_with_a_different_key() -> None:
    original_tokens = HmacInvitationTokens(
        b"original-signing-key-with-32-bytes!!", timedelta(days=1)
    )
    changed_tokens = HmacInvitationTokens(
        b"changed-signing-key-with-32-bytes!!!", timedelta(days=1)
    )
    invitation_id = InvitationId.new()
    issued = original_tokens.issue(invitation_id=invitation_id, issued_at=NOW)
    invitation = Invitation.issue(
        invitation_id=invitation_id,
        invited_by=make_employee("admin@example.com").id,
        invited_email=Email("employee@example.com"),
        roles=(EmployeeRole.AUDITOR,),
        token_hash=issued.token_hash,
        created_at=NOW,
        expires_at=issued.expires_at,
    )
    sender = EmailSenderFake()
    deliver = DeliverInvitationEmail(
        uow=UnitOfWorkFake(),
        clock=FixedClock(NOW),
        invitations=InvitationRepositoryFake((invitation,)),
        token_issuer=changed_tokens,
        token_verifier=changed_tokens,
        email_sender=sender,
    )

    with pytest.raises(InvitationDeliveryError, match="Invitation token does not match"):
        asyncio.run(
            deliver.execute(
                InvitationEmailRequested(
                    invitation_id=invitation.id.value,
                    recipient_email=invitation.invited_email.value,
                )
            )
        )

    assert sender.sent == []
