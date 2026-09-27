from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RevokeOwnSessionCommand:
    employee_id: UUID
    target_session_id: UUID
