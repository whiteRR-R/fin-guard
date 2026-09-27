from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ListOwnSessionsQuery:
    employee_id: UUID
    current_session_id: UUID
