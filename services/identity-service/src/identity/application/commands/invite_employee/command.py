from dataclasses import dataclass
from uuid import UUID

from identity.domain.enums.role import EmployeeRole


@dataclass(frozen=True)
class InviteEmployeeCommand:
    actor_id: UUID
    employee_email: str
    employee_roles: tuple[EmployeeRole]
