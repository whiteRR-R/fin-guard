from dataclasses import dataclass, field
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionLoggedOut(OutboxMessage):
    session_id: UUID
    employee_id: UUID
    version: int = field(default=1, init=False)
