from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeBlockedMessage(OutboxMessage):
    message_type: ClassVar[str] = "EmployeeBlocked"

    employee_id: UUID
    actor_id: UUID
    revoked_session_ids: tuple[UUID, ...]
    version: int = field(default=1, init=False)
