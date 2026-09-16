from identity.application.commands.unblock_employee.command import UnblockUserCommand
from identity.application.commands.unblock_employee.result import UnblockUserResult
from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotFoundError,
)
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.exceptions import EmployeeUnblockNotAllowedError
from identity.domain.policies.employee_unblock import EmployeeUnblockPolicy
from identity.domain.value_objects.employee_id import EmployeeId


class UnblockUserHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        employees: EmployeeRepository,
        unblock_policy: EmployeeUnblockPolicy,
    ) -> None:
        self._uow = uow
        self._employees = employees
        self._unblock_policy = unblock_policy

    async def execute(self, command: UnblockUserCommand) -> UnblockUserResult:
        target_id = EmployeeId(command.target_id)
        actor_id = EmployeeId(command.actor_id)

        async with self._uow:
            actor = await self._employees.get_by_id(actor_id)

            if actor is None:
                raise AuthenticationError("Invalid actor")

            target = await self._employees.get_by_id(target_id)

            if target is None:
                raise EmployeeNotFoundError("User not found")

            try:
                self._unblock_policy.ensure_allowed(actor=actor, target=target)
            except EmployeeUnblockNotAllowedError as error:
                raise AccessDeniedError("User unblocking is not allowed") from error

            target.unblock()

            await self._employees.save(target)
            await self._uow.commit()

        return UnblockUserResult(user_id=target.id.value, status=target.status.value)
