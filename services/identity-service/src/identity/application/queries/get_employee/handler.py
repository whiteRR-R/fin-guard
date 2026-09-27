from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
    EmployeeNotFoundError,
)
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.application.queries.get_employee.query import GetEmployeeQuery
from identity.application.queries.get_employee.result import GetEmployeeResult
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId


class GetEmployeeHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        employee_repository: EmployeeRepository,
    ) -> None:
        self._uow = uow
        self._employee_repository = employee_repository

    async def execute(self, query: GetEmployeeQuery) -> GetEmployeeResult:
        actor_id = EmployeeId(query.actor_id)
        employee_id = EmployeeId(query.employee_id)

        async with self._uow:
            actor = await self._employee_repository.get_by_id(actor_id)

            if actor is None:
                raise AuthenticationError("Invalid actor")

            if actor.status is not EmployeeStatus.ACTIVE:
                raise EmployeeNotActiveError("Actor must be active")

            allowed_roles = {EmployeeRole.ADMIN, EmployeeRole.COMPLIANCE_OFFICER}

            if allowed_roles.isdisjoint(actor.roles):
                raise AccessDeniedError("Access denied")

            employee = await self._employee_repository.get_by_id(employee_id)

            if employee is None:
                raise EmployeeNotFoundError("Employee not found")

            result = GetEmployeeResult(
                employee_id=employee.id.value,
                email=employee.email.value,
                status=employee.status,
                roles=tuple(sorted(employee.roles, key=lambda role: role.value)),
            )

        return result
