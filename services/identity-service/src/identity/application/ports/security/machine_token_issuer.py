from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from identity.domain.enums.scope import MachineScope
from identity.domain.value_objects.service_account import ClientId, ServiceAccountId


@dataclass(frozen=True, slots=True)
class IssuedMachineToken:
    plain_token: str = field(repr=False)
    expires_at: datetime


class MachineTokenIssuer(Protocol):
    def issue(
        self,
        *,
        service_account_id: ServiceAccountId,
        client_id: ClientId,
        scopes: frozenset[MachineScope],
        issued_at: datetime,
    ) -> IssuedMachineToken: ...
