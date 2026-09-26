from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class BlockEmployeeResult:
    employee_id: UUID
    status: str
