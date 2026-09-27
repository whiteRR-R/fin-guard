from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GetEmployeeQuery:
    actor_id: UUID
    employee_id: UUID
