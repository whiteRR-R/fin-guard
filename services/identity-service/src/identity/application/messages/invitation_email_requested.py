from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class InvitationEmailRequestedMessage(OutboxMessage):
    message_type: ClassVar[str] = "InvitationEmailRequested"

    invitation_id: UUID
    recipient_email: str
    version: int = field(default=1, init=False)
