from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ListEmployeesQuery:
    actor_id: UUID
    limit: int = 50
    offset: int = 0
