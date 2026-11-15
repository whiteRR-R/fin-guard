from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class ClientSecretRotatedMessage(OutboxMessage):
    message_type: ClassVar[str] = "ClientSecretRotated"

    service_account_id: UUID
    actor_id: UUID
    previous_secret_expires_at: datetime | None
    version: int = field(default=1, init=False)
