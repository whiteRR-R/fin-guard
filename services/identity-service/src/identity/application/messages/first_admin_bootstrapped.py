from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from identity.application.messages.base import OutboxMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class FirstAdminBootstrappedMessage(OutboxMessage):
    message_type: ClassVar[str] = "FirstAdminBootstrapped"

    employee_id: UUID
    version: int = field(default=1, init=False)
