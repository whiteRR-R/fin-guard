from dataclasses import dataclass, field
from uuid import UUID

from identity.application.messages.base import OutboxMessage
from identity.domain.enums.role import EmployeeRole


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeRoleAssigned(OutboxMessage):
    employee_id: UUID
    actor_id: UUID
    role: EmployeeRole
    version: int = field(default=1, init=False)
