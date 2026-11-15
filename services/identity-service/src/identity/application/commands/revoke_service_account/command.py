from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RevokeServiceAccountCommand:
    actor_id: UUID
    service_account_id: UUID
