from dataclasses import dataclass, field
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionRevoked(OutboxMessage):
    employee_id: UUID
    session_id: UUID
    version: int = field(default=1, init=False)
