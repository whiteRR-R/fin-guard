import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from identity.application.commands.accept_invitation.command import (
    AcceptInvitationCommand,
)
from identity.application.commands.accept_invitation.handler import (
    AcceptInvitationHandler,
)
from identity.application.commands.revoke_invitation.command import (
    RevokeInvitationCommand,
)
from identity.application.commands.revoke_invitation.handler import (
    RevokeInvitationHandler,
)
from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
    InvitationNotFoundError,
)
from identity.application.messages.invitation_revoked import InvitationRevoked
from identity.application.ports.security.invitation_token_verifier import (
    InvitationTokenClaims,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.invitation import Invitation
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.domain.events.invitation import (
    InvitationRevoked as InvitationRevokedEvent,
)
from identity.domain.exceptions import (
    InvitationAlreadyAcceptedError,
    InvitationExpiredError,
    InvitationRevokedError,
)
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash
from tests.unit.application.doubles import (
    FixedClock,
    InvitationTokenVerifierStub,
    PasswordHasherStub,
)
from tests.unit.application.factories import make_employee
from tests.unit.application.onboarding_support import (
    OnboardingContext,
    OnboardingStore,
    make_context,
)

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


@pytest.fixture
def admin() -> EmployeeAccount:
    return make_employee(
        "admin@example.com", roles=(EmployeeRole.ADMIN, EmployeeRole.AUDITOR)
    )


@pytest.fixture
def invitee() -> EmployeeAccount:
    return make_employee("employee@example.com", status=EmployeeStatus.INVITED)


@pytest.fixture
def invitation(admin: EmployeeAccount, invitee: EmployeeAccount) -> Invitation:
    return Invitation.issue(
        invitation_id=InvitationId.new(),
        invited_by=admin.id,
        invited_email=invitee.email,
        roles=invitee.roles,
        token_hash=InvitationTokenHash("invitation-hash"),
        created_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
    )


@pytest.fixture
def store(
    admin: EmployeeAccount, invitee: EmployeeAccount, invitation: Invitation
) -> OnboardingStore:
    store = OnboardingStore()
    store.state.employees = {employee.id: employee for employee in (admin, invitee)}
    store.state.invitations[invitation.id] = invitation
    return store


def make_handler(
    context: OnboardingContext, *, now: datetime = NOW
) -> RevokeInvitationHandler:
    return RevokeInvitationHandler(
        uow=context.uow,
        clock=FixedClock(now),
        employees=context.employees,
        invitations=context.invitations,
        outbox=context.outbox,
    )


def test_admin_revokes_invitation_and_records_audit(
    store: OnboardingStore,
    admin: EmployeeAccount,
    invitee: EmployeeAccount,
    invitation: Invitation,
) -> None:
    context = make_context(store)

    asyncio.run(
        make_handler(context).execute(
            RevokeInvitationCommand(admin.id.value, invitation.id.value)
        )
    )

    saved = store.state.invitations[invitation.id]
    assert saved.status is InvitationStatus.REVOKED
    assert saved.revoked_at == NOW
    assert store.state.employees[invitee.id].status is EmployeeStatus.INVITED
    events = saved.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], InvitationRevokedEvent)
    assert len(store.state.messages) == 1
    message = store.state.messages[0]
    assert isinstance(message, InvitationRevoked)
    assert message.actor_id == admin.id.value
    assert message.invitation_id == invitation.id.value
    assert message.created_at == NOW
    assert message.version == 1
    assert "invitation-hash" not in repr(message)
    context.invitations.get_by_id_with_lock.assert_awaited_once_with(invitation.id)
    context.employees.save.assert_not_awaited()
    assert context.uow.commit_count == 1


@pytest.mark.parametrize(
    "role",
    [EmployeeRole.RISK_ANALYST, EmployeeRole.AUDITOR, EmployeeRole.COMPLIANCE_OFFICER],
)
def test_non_admin_cannot_revoke(
    store: OnboardingStore, invitation: Invitation, role: EmployeeRole
) -> None:
    actor = make_employee("actor@example.com", roles=(role,))
    store.state.employees[actor.id] = actor
    context = make_context(store)

    with pytest.raises(AccessDeniedError):
        asyncio.run(
            make_handler(context).execute(
                RevokeInvitationCommand(actor.id.value, invitation.id.value)
            )
        )

    context.invitations.get_by_id_with_lock.assert_not_awaited()
    assert store.state.messages == []
    assert context.uow.commit_count == 0


@pytest.mark.parametrize(
    "status",
    [EmployeeStatus.INVITED, EmployeeStatus.BLOCKED, EmployeeStatus.DEACTIVATED],
)
def test_inactive_admin_cannot_revoke(
    store: OnboardingStore, invitation: Invitation, status: EmployeeStatus
) -> None:
    actor = make_employee("actor@example.com", roles=(EmployeeRole.ADMIN,), status=status)
    store.state.employees[actor.id] = actor
    context = make_context(store)

    with pytest.raises(EmployeeNotActiveError):
        asyncio.run(
            make_handler(context).execute(
                RevokeInvitationCommand(actor.id.value, invitation.id.value)
            )
        )

    context.invitations.get_by_id_with_lock.assert_not_awaited()
    assert context.uow.commit_count == 0


def test_missing_actor_cannot_revoke(
    store: OnboardingStore, invitation: Invitation
) -> None:
    context = make_context(store)

    with pytest.raises(AuthenticationError):
        asyncio.run(
            make_handler(context).execute(
                RevokeInvitationCommand(EmployeeId.new().value, invitation.id.value)
            )
        )

    context.invitations.get_by_id_with_lock.assert_not_awaited()


def test_missing_invitation_is_reported(
    store: OnboardingStore, admin: EmployeeAccount
) -> None:
    context = make_context(store)

    with pytest.raises(InvitationNotFoundError):
        asyncio.run(
            make_handler(context).execute(
                RevokeInvitationCommand(admin.id.value, InvitationId.new().value)
            )
        )

    assert store.state.messages == []
    assert context.uow.commit_count == 0


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (InvitationStatus.ACCEPTED, InvitationAlreadyAcceptedError),
        (InvitationStatus.REVOKED, InvitationRevokedError),
    ],
)
def test_final_invitation_status_cannot_be_revoked(
    store: OnboardingStore,
    admin: EmployeeAccount,
    invitation: Invitation,
    status: InvitationStatus,
    error: type[Exception],
) -> None:
    if status is InvitationStatus.ACCEPTED:
        invitation.accept(NOW - timedelta(minutes=1))
    else:
        invitation.revoke(NOW - timedelta(minutes=1))
    invitation.pull_events()
    context = make_context(store)

    with pytest.raises(error):
        asyncio.run(
            make_handler(context).execute(
                RevokeInvitationCommand(admin.id.value, invitation.id.value)
            )
        )

    assert store.state.invitations[invitation.id].status is status
    assert store.state.messages == []
    context.invitations.save.assert_not_awaited()


def test_invitation_cannot_be_revoked_at_expiration(
    store: OnboardingStore, admin: EmployeeAccount, invitation: Invitation
) -> None:
    context = make_context(store)

    with pytest.raises(InvitationExpiredError):
        asyncio.run(
            make_handler(context, now=invitation.expires_at).execute(
                RevokeInvitationCommand(admin.id.value, invitation.id.value)
            )
        )

    assert store.state.invitations[invitation.id].status is InvitationStatus.PENDING
    assert store.state.messages == []


@pytest.mark.parametrize("failure", ["outbox", "commit"])
def test_failed_revoke_rolls_back_status_and_audit(
    store: OnboardingStore, admin: EmployeeAccount, invitation: Invitation, failure: str
) -> None:
    context = make_context(store)
    context.uow.fail_commit = failure == "commit"
    if failure == "outbox":
        context.outbox.add.side_effect = RuntimeError("Outbox failed")

    with pytest.raises(RuntimeError):
        asyncio.run(
            make_handler(context).execute(
                RevokeInvitationCommand(admin.id.value, invitation.id.value)
            )
        )

    assert store.state.invitations[invitation.id].status is InvitationStatus.PENDING
    assert store.state.invitations[invitation.id].revoked_at is None
    assert store.state.messages == []
    assert context.uow.rollback_count == 1


@pytest.mark.parametrize("revoke_first", [True, False])
def test_accept_and_revoke_cannot_both_succeed(
    store: OnboardingStore,
    admin: EmployeeAccount,
    invitee: EmployeeAccount,
    invitation: Invitation,
    revoke_first: bool,
) -> None:
    async def run_concurrently() -> list[None | BaseException]:
        revoke_context = make_context(store)
        accept_context = make_context(store)
        accept = AcceptInvitationHandler(
            uow=accept_context.uow,
            clock=FixedClock(NOW),
            employees=accept_context.employees,
            invitations=accept_context.invitations,
            password_hasher=PasswordHasherStub(password_is_valid=True),
            invitation_verifier=InvitationTokenVerifierStub(
                InvitationTokenClaims(invitation_id=invitation.id.value)
            ),
        )
        revoke_operation = make_handler(revoke_context).execute(
            RevokeInvitationCommand(admin.id.value, invitation.id.value)
        )
        accept_operation = accept.execute(
            AcceptInvitationCommand("token", "valid-password-123")
        )
        operations = (
            (revoke_operation, accept_operation)
            if revoke_first
            else (accept_operation, revoke_operation)
        )
        return await asyncio.gather(*operations, return_exceptions=True)

    results = asyncio.run(run_concurrently())

    assert sum(result is None for result in results) == 1
    if revoke_first:
        assert isinstance(results[1], InvitationRevokedError)
        assert store.state.invitations[invitation.id].status is InvitationStatus.REVOKED
        assert store.state.employees[invitee.id].status is EmployeeStatus.INVITED
        assert len(store.state.messages) == 1
    else:
        assert isinstance(results[1], InvitationAlreadyAcceptedError)
        assert store.state.invitations[invitation.id].status is InvitationStatus.ACCEPTED
        assert store.state.employees[invitee.id].status is EmployeeStatus.ACTIVE
        assert store.state.messages == []
