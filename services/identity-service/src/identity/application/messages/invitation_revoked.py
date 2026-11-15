from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class InvitationRevokedMessage(OutboxMessage):
    message_type: ClassVar[str] = "InvitationRevoked"

    invitation_id: UUID
    actor_id: UUID
    version: int = field(default=1, init=False)
