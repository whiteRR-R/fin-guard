from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RotateClientSecretCommand:
    actor_id: UUID
    service_account_id: UUID
