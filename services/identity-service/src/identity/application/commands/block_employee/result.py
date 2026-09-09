from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class BlockUserResult:
    user_id: UUID
    status: str
