from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeEmailChangedMessage(OutboxMessage):
    message_type: ClassVar[str] = "EmployeeEmailChanged"

    employee_id: UUID
    version: int = field(default=1, init=False)
