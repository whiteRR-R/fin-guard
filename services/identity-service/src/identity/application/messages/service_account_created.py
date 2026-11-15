from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage
from identity.domain.enums.scope import MachineScope


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceAccountCreatedMessage(OutboxMessage):
    message_type: ClassVar[str] = "ServiceAccountCreated"

    service_account_id: UUID
    client_id: str
    actor_id: UUID
    scopes: tuple[MachineScope, ...]
    version: int = field(default=1, init=False)
