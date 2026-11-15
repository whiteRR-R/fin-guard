from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from identity.domain.aggregates.service_account import ServiceAccount
from identity.domain.enums.scope import MachineScope
from identity.domain.enums.status import ServiceAccountStatus


@dataclass(frozen=True, slots=True)
class ClientSecretView:
    secret_id: UUID
    created_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ServiceAccountView:
    service_account_id: UUID
    client_id: str
    name: str
    scopes: tuple[MachineScope, ...]
    status: ServiceAccountStatus
    created_by: UUID
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None
    active_secrets: tuple[ClientSecretView, ...]

    @classmethod
    def from_aggregate(
        cls, account: ServiceAccount, now: datetime
    ) -> "ServiceAccountView":
        return cls(
            service_account_id=account.id.value,
            client_id=account.client_id.value,
            name=account.name.value,
            scopes=tuple(sorted(account.scopes, key=lambda scope: scope.value)),
            status=account.status,
            created_by=account.created_by.value,
            created_at=account.created_at,
            revoked_at=account.revoked_at,
            last_used_at=account.last_used_at,
            active_secrets=tuple(
                ClientSecretView(
                    secret_id=secret.id.value,
                    created_at=secret.created_at,
                    expires_at=secret.expires_at,
                )
                for secret in sorted(
                    account.active_secrets(now), key=lambda item: item.created_at
                )
            ),
        )
