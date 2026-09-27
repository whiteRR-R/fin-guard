from dataclasses import dataclass, field
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class AllSessionsLoggedOut(OutboxMessage):
    employee_id: UUID
    revoked_sessions_count: int
    version: int = field(default=1, init=False)
