from dataclasses import dataclass
from uuid import UUID

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus


@dataclass(frozen=True, slots=True)
class EmployeeListItem:
    employee_id: UUID
    email: str
    status: EmployeeStatus
    roles: tuple[EmployeeRole, ...]


@dataclass(frozen=True, slots=True)
class ListEmployeesResult:
    employees: tuple[EmployeeListItem, ...]
    limit: int
    offset: int
    has_more: bool
