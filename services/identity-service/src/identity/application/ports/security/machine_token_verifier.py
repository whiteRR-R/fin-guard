from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from identity.domain.enums.scope import MachineScope
from identity.domain.value_objects.service_account import ClientId, ServiceAccountId


@dataclass(frozen=True, kw_only=True, slots=True)
class MachineTokenClaims:
    service_account_id: ServiceAccountId
    client_id: ClientId
    scopes: frozenset[MachineScope]
    expires_at: datetime


class MachineTokenVerifier(Protocol):
    def verify(self, access_token: str) -> MachineTokenClaims: ...
