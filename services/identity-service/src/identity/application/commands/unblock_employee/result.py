from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class UnblockUserResult:
    user_id: UUID
    status: str
