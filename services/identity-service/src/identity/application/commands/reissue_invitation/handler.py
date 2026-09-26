from identity.application.commands.reissue_invitation.command import (
    ReissueInvitationCommand,
)
from identity.application.commands.reissue_invitation.result import (
    ReissueInvitationResult,
)
from identity.application.exceptions import (
    AuthenticationError,
    EmployeeIsNotInvitedError,
    EmployeeNotFoundError,
    InvitationCannotBeReissuedError,
    InvitationNotFoundError,
)
from identity.application.messages.invitation_email_requested import (
    InvitationEmailRequested,
)
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.security.invitation_token_issuer import (
    InvitationTokenIssuer,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.aggregates.invitation import Invitation
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId


class ReissueInvitationHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        outbox: OutboxRepository,
        employees: EmployeeRepository,
        invitations: InvitationRepository,
        invitation_policy: EmployeeInvitePolicy,
        invitation_token_issuer: InvitationTokenIssuer,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._outbox = outbox
        self._employees = employees
        self._invitations = invitations
        self._invitation_policy = invitation_policy
        self._invitation_token_issuer = invitation_token_issuer

    async def execute(
        self,
        command: ReissueInvitationCommand,
    ) -> ReissueInvitationResult:

        inviter_id = EmployeeId(command.inviter_id)
        invited_email = Email(command.employee_email)

        async with self._uow:
            inviter = await self._employees.get_by_id(inviter_id)

            if inviter is None:
                raise AuthenticationError("Inviter not found")

            self._invitation_policy.ensure_allowed(inviter)

            invited_employee = await self._employees.get_by_email(invited_email)

            if invited_employee is None:
                raise EmployeeNotFoundError("Employee not found")

            if invited_employee.status is not EmployeeStatus.INVITED:
                raise EmployeeIsNotInvitedError(
                    "Only an invited employee can receive a new invitation"
                )

            current_invitation = await self._invitations.get_latest_by_employee_email(
                invited_email
            )

            if current_invitation is None:
                raise InvitationNotFoundError("Inivation not found")

            if current_invitation.status is InvitationStatus.ACCEPTED:
                raise InvitationCannotBeReissuedError(
                    "Accepted invitation cannot be reissued"
                )

            now = self._clock.now()

            if (
                current_invitation.status is InvitationStatus.PENDING
                and not current_invitation.is_expired(now)
            ):
                current_invitation.revoke(now)
                await self._invitations.save(current_invitation)

            new_invitation_id = InvitationId.new()

            issued_invitation_token = self._invitation_token_issuer.issue(
                invitation_id=new_invitation_id,
                issued_at=now,
            )

            new_invitation = Invitation.issue(
                invitation_id=new_invitation_id,
                invited_by=inviter.id,
                invited_email=invited_email,
                token_hash=issued_invitation_token.token_hash,
                roles=invited_employee.roles,
                created_at=now,
                expires_at=issued_invitation_token.expires_at,
            )

            outbox_message = InvitationEmailRequested(
                invitation_id=new_invitation_id.value,
                recipient_email=invited_email.value,
            )
            await self._invitations.add(new_invitation)
            await self._outbox.add(outbox_message)
            await self._uow.commit()

        return ReissueInvitationResult(
            invitation_id=new_invitation.id.value,
            inviter_id=inviter_id.value,
            employee_id=invited_employee.id.value,
        )
