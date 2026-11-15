from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RotateClientSecretResult:
    service_account_id: UUID
    client_id: str
    client_secret: str = field(repr=False)
    previous_secret_expires_at: datetime | None
