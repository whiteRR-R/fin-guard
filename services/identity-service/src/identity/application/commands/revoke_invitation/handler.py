from identity.application.commands.revoke_invitation.command import (
    RevokeInvitationCommand,
)
from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
    InvitationNotFoundError,
)
from identity.application.messages.invitation_revoked import InvitationRevoked
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId


class RevokeInvitationHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        employees: EmployeeRepository,
        invitations: InvitationRepository,
        outbox: OutboxRepository,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._employees = employees
        self._invitations = invitations
        self._outbox = outbox

    async def execute(self, command: RevokeInvitationCommand) -> None:
        actor_id = EmployeeId(command.actor_id)
        invitation_id = InvitationId(command.invitation_id)

        async with self._uow:
            actor = await self._employees.get_by_id(actor_id)

            if actor is None:
                raise AuthenticationError("Invalid actor")

            if actor.status is not EmployeeStatus.ACTIVE:
                raise EmployeeNotActiveError("Actor must be active")

            if EmployeeRole.ADMIN not in actor.roles:
                raise AccessDeniedError("Only an administrator can revoke invitations")

            invitation = await self._invitations.get_by_id_with_lock(invitation_id)

            if invitation is None:
                raise InvitationNotFoundError("Invitation not found")

            now = self._clock.now()
            invitation.revoke(now)

            await self._invitations.save(invitation)
            await self._outbox.add(
                InvitationRevoked(
                    invitation_id=invitation.id.value,
                    actor_id=actor.id.value,
                    created_at=now,
                )
            )
            await self._uow.commit()
