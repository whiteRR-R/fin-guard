from identity.application.commands.revoke_role.command import RevokeRoleCommand
from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
    EmployeeNotFoundError,
    LastActiveAdminError,
)
from identity.application.messages.employee_role_revoked import EmployeeRoleRevoked
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId


class RevokeRoleHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        employees: EmployeeRepository,
        outbox: OutboxRepository,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._employees = employees
        self._outbox = outbox

    async def execute(self, command: RevokeRoleCommand) -> None:
        actor_id = EmployeeId(command.actor_id)
        employee_id = EmployeeId(command.employee_id)

        async with self._uow:
            await self._employees.lock_role_changes()

            actor = await self._employees.get_by_id(actor_id)

            if actor is None:
                raise AuthenticationError("Invalid actor")

            if actor.status is not EmployeeStatus.ACTIVE:
                raise EmployeeNotActiveError("Actor must be active")

            if EmployeeRole.ADMIN not in actor.roles:
                raise AccessDeniedError("Only an administrator can revoke roles")

            employee = await self._employees.get_by_id_with_lock(employee_id)

            if employee is None:
                raise EmployeeNotFoundError("Employee not found")

            if (
                command.role is EmployeeRole.ADMIN
                and EmployeeRole.ADMIN in employee.roles
                and employee.status is EmployeeStatus.ACTIVE
                and await self._employees.count_active_admins() <= 1
            ):
                raise LastActiveAdminError("Cannot revoke the last active admin role")

            previous_roles = employee.roles
            employee.revoke_role(command.role)

            if employee.roles == previous_roles:
                return

            await self._employees.save(employee)
            await self._outbox.add(
                EmployeeRoleRevoked(
                    employee_id=employee.id.value,
                    actor_id=actor.id.value,
                    role=command.role,
                    created_at=self._clock.now(),
                )
            )
            await self._uow.commit()
