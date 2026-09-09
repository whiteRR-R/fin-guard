from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class ChangeEmailCommand:
    user_id: UUID
    new_email: str
    password: str = field(repr=False)
