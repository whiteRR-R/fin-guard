from dataclasses import dataclass
from uuid import UUID

from identity.domain.enums.role import EmployeeRole


@dataclass(frozen=True, slots=True)
class RevokeRoleCommand:
    actor_id: UUID
    employee_id: UUID
    role: EmployeeRole
