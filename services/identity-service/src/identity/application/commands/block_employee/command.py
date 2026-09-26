from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class BlockEmployeeCommand:
    target_id: UUID
    actor_id: UUID
