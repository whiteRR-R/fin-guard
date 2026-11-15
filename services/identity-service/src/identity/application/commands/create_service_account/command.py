from dataclasses import dataclass
from uuid import UUID

from identity.domain.enums.scope import MachineScope


@dataclass(frozen=True, slots=True)
class CreateServiceAccountCommand:
    actor_id: UUID
    name: str
    scopes: tuple[MachineScope, ...]
