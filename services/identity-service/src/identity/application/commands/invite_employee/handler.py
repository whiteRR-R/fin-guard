from identity.application.commands.invite_employee.command import InviteEmployeeCommand
from identity.application.commands.invite_employee.result import InviteEmployeeResult
from identity.application.exceptions import (
    AuthenticationError,
    EmployeeAlreadyInvitedError,
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
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.invitation import Invitation
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId


class InviteEmployeeHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        outbox: OutboxRepository,
        employees: EmployeeRepository,
        invitations: InvitationRepository,
        invite_policy: EmployeeInvitePolicy,
        invitation_token_issuer: InvitationTokenIssuer,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._outbox = outbox
        self._employees = employees
        self._invitations = invitations
        self._invite_policy = invite_policy
        self._invitation_token_issuer = invitation_token_issuer

    async def execute(self, command: InviteEmployeeCommand) -> InviteEmployeeResult:
        inviter_id = EmployeeId(command.inviter_id)
        employee_email = Email(command.employee_email)
        requested_roles = command.employee_roles

        async with self._uow:
            inviter = await self._employees.get_by_id(inviter_id)

            if inviter is None:
                raise AuthenticationError("Inviter not found")

            self._invite_policy.ensure_allowed(inviter)

            existing_employee = await self._employees.get_by_email(employee_email)

            if existing_employee is not None:
                raise EmployeeAlreadyInvitedError("Employee already invited")

            now = self._clock.now()

            invitation_id = InvitationId.new()
            employee_id = EmployeeId.new()

            issued_invitation_token = self._invitation_token_issuer.issue(
                invitation_id=invitation_id,
                invited_by=inviter.id,
                employee_email=employee_email,
                issued_at=now,
            )

            employee = EmployeeAccount.invite(
                employee_id=employee_id, email=employee_email, roles=requested_roles
            )
            
            invitation = Invitation.issue(
                invitation_id=invitation_id,
                invited_by=inviter.id,
                invited_email=employee_email,
                token_hash=issued_invitation_token.token_hash,
                roles=requested_roles,
                created_at=now,
                expires_at=issued_invitation_token.expires_at,
            )
            
            email_message = InvitationEmailRequested(
                invitation_id=invitation_id.value,
                recipient_email=employee_email.value
            )

            await self._employees.add(employee)
            await self._invitations.add(invitation)
            await self._outbox.add(email_message)

            await self._uow.commit()

        return InviteEmployeeResult(
            invitation_id=invitation_id.value,
            employee_id=employee.id.value,
        )
