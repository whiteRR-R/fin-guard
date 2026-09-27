from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class LogoutCommand:
    employee_id: UUID
    session_id: UUID
