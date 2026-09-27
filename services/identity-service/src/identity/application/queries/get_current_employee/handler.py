from identity.application.exceptions import EmployeeNotActiveError, EmployeeNotFoundError
from identity.application.ports.repositories.employee_repository import EmployeeRepository
from identity.application.ports.unit_of_work import UnitOfWork
from identity.application.queries.get_current_employee.query import GetCurrentEmployeeQuery
from identity.application.queries.get_current_employee.result import EmployeeInfoResult
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId


class GetCurrentEmployeeHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        employee_repository: EmployeeRepository,
    ) -> None:
        self._uow = uow
        self._employee_repository = employee_repository

    async def execute(self, query: GetCurrentEmployeeQuery) -> EmployeeInfoResult:
        employee_id = EmployeeId(query.employee_id)

        async with self._uow:
            employee = await self._employee_repository.get_by_id(employee_id)

            if employee is None:
                raise EmployeeNotFoundError("Employee not found")

            if employee.status is not EmployeeStatus.ACTIVE:
                raise EmployeeNotActiveError("Employee must be active")

            result = EmployeeInfoResult(
                employee_id=employee.id.value,
                email=employee.email.value,
                status=employee.status,
                roles=tuple(sorted(employee.roles, key=lambda role: role.value)),
            )

        return result
