from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class UnblockUserCommand:
    target_id: UUID
    actor_id: UUID
