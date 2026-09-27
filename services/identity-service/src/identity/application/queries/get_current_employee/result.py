from dataclasses import dataclass
from uuid import UUID

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus


@dataclass(frozen=True, slots=True)
class EmployeeInfoResult:
    employee_id: UUID
    email: str
    status: EmployeeStatus
    roles: tuple[EmployeeRole, ...]
