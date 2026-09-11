from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class InviteEmployeeResult:
    invitation_id: UUID
    employee_id: UUID
    