
from dataclasses import dataclass
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class InvitationEmailRequested(OutboxMessage):
    invitation_id: UUID
    recipient_email: str
    
