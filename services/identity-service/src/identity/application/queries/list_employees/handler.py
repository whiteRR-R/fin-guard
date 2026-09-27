from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
    InvalidPaginationError,
)
from identity.application.ports.repositories.employee_repository import EmployeeRepository
from identity.application.ports.unit_of_work import UnitOfWork
from identity.application.queries.list_employees.query import ListEmployeesQuery
from identity.application.queries.list_employees.result import (
    EmployeeListItem,
    ListEmployeesResult,
)
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId


class ListEmployeesHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        employee_repository: EmployeeRepository,
    ) -> None:
        self._uow = uow
        self._employee_repository = employee_repository

    async def execute(self, query: ListEmployeesQuery) -> ListEmployeesResult:
        if type(query.limit) is not int or not 1 <= query.limit <= 100:
            raise InvalidPaginationError("Limit must be an integer between 1 and 100")

        if type(query.offset) is not int or query.offset < 0:
            raise InvalidPaginationError("Offset must be a non-negative integer")

        actor_id = EmployeeId(query.actor_id)

        async with self._uow:
            actor = await self._employee_repository.get_by_id(actor_id)

            if actor is None:
                raise AuthenticationError("Invalid actor")

            if actor.status is not EmployeeStatus.ACTIVE:
                raise EmployeeNotActiveError("Actor must be active")

            allowed_roles = {EmployeeRole.ADMIN, EmployeeRole.COMPLIANCE_OFFICER}

            if allowed_roles.isdisjoint(actor.roles):
                raise AccessDeniedError("Access denied")

            employees = await self._employee_repository.list_page(
                limit=query.limit + 1,
                offset=query.offset,
            )
            result = ListEmployeesResult(
                employees=tuple(
                    EmployeeListItem(
                        employee_id=employee.id.value,
                        email=employee.email.value,
                        status=employee.status,
                        roles=tuple(sorted(employee.roles, key=lambda role: role.value)),
                    )
                    for employee in employees[: query.limit]
                ),
                limit=query.limit,
                offset=query.offset,
                has_more=len(employees) > query.limit,
            )

        return result
