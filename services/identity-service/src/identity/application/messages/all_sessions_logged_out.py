from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class AllSessionsLoggedOutMessage(OutboxMessage):
    message_type: ClassVar[str] = "AllSessionsLoggedOut"

    employee_id: UUID
    revoked_sessions_count: int
    version: int = field(default=1, init=False)
