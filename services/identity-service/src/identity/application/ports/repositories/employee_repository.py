from typing import Protocol

from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId


class EmployeeRepository(Protocol):
    async def has_admin(self) -> bool: ...

    async def lock_role_changes(self) -> None: ...

    async def count_active_admins(self) -> int: ...

    async def get_by_id_with_lock(
        self, employee_id: EmployeeId
    ) -> EmployeeAccount | None: ...

    async def get_by_id(self, employee_id: EmployeeId) -> EmployeeAccount | None: ...

    async def get_by_email(self, email: Email) -> EmployeeAccount | None: ...

    async def get_by_email_with_lock(
        self, email: Email
    ) -> EmployeeAccount | None: ...

    async def list_page(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[EmployeeAccount]: ...

    async def add(self, employee: EmployeeAccount) -> None: ...

    async def save(self, employee: EmployeeAccount) -> None: ...
