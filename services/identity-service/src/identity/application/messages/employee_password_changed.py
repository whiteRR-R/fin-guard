from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeePasswordChangedMessage(OutboxMessage):
    message_type: ClassVar[str] = "EmployeePasswordChanged"

    employee_id: UUID
    revoked_session_ids: tuple[UUID, ...]
    version: int = field(default=1, init=False)
