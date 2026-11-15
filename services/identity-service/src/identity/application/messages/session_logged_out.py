from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionLoggedOutMessage(OutboxMessage):
    message_type: ClassVar[str] = "SessionLoggedOut"

    session_id: UUID
    employee_id: UUID
    version: int = field(default=1, init=False)
