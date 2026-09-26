from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class UnblockEmployeeResult:
    employee_id: UUID
    status: str
