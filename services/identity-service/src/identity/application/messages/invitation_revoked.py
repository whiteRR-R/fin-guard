from dataclasses import dataclass, field
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class InvitationRevoked(OutboxMessage):
    invitation_id: UUID
    actor_id: UUID
    version: int = field(default=1, init=False)
