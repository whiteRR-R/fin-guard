from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from identity.domain.enums.scope import MachineScope


@dataclass(frozen=True, slots=True)
class CreateServiceAccountResult:
    service_account_id: UUID
    client_id: str
    client_secret: str = field(repr=False)
    scopes: tuple[MachineScope, ...]
    created_at: datetime
