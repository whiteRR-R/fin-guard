from typing import Protocol

from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId


class EmployeeRepository(Protocol):
    async def get_by_id(self, id: EmployeeId) -> EmployeeAccount | None: ...

    async def get_by_email(self, email: Email) -> EmployeeAccount | None: ...

    async def add(self, employee: EmployeeAccount) -> None: ...

    async def save(self, employee: EmployeeAccount) -> None: ...
