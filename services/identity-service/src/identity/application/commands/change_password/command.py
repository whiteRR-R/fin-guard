from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class ChangePasswordCommand:
    employee_id: UUID
    current_password: str = field(repr=False)
    new_password: str = field(repr=False)
