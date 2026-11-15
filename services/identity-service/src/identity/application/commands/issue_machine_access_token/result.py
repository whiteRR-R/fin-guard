from dataclasses import dataclass, field
from datetime import datetime

from identity.domain.enums.scope import MachineScope


@dataclass(frozen=True, slots=True)
class IssueMachineAccessTokenResult:
    access_token: str = field(repr=False)
    expires_at: datetime
    scopes: tuple[MachineScope, ...]
    token_type: str = "Bearer"
