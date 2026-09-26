from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class ChangeEmailCommand:
    employee_id: UUID
    new_email: str
    password: str = field(repr=False)
