from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from identity.application.ports.security.client_credentials import IssuedClientSecret
from identity.application.ports.security.machine_token_issuer import (
    IssuedMachineToken,
)
from identity.domain.aggregates.service_account import ServiceAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.scope import MachineScope
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.service_account import (
    ClientId,
    ClientSecretHash,
    ClientSecretId,
    ServiceAccountId,
    ServiceAccountName,
)

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
CLIENT_ID = "sa_" + "c" * 32
PLAIN_SECRET = "plain-secret-1"
GRACE = timedelta(hours=24)


def hash_of(plain_secret: str) -> ClientSecretHash:
    return ClientSecretHash(f"hash:{plain_secret}")


def make_service_account(
    *,
    client_id: str = CLIENT_ID,
    scopes: Iterable[MachineScope] = (
        MachineScope.TRANSACTIONS_WRITE,
        MachineScope.TRANSACTIONS_READ,
    ),
    plain_secret: str = PLAIN_SECRET,
    created_at: datetime = NOW,
) -> ServiceAccount:
    account = ServiceAccount.create(
        service_account_id=ServiceAccountId.new(),
        client_id=ClientId(client_id),
        name=ServiceAccountName("Bank X backend"),
        scopes=scopes,
        created_by=EmployeeId.new(),
        secret_id=ClientSecretId.new(),
        secret_hash=hash_of(plain_secret),
        created_at=created_at,
    )
    account.pull_events()
    return account


ADMIN_ROLES = (EmployeeRole.ADMIN,)


class ServiceAccountRepositoryFake:
    def __init__(self, accounts: Iterable[ServiceAccount] = ()) -> None:
        self._accounts = {account.id: account for account in accounts}
        self.added: list[ServiceAccount] = []
        self.saved: list[ServiceAccount] = []
        self.usage_saved: list[ServiceAccount] = []
        self.locked_ids: list[ServiceAccountId] = []
        self.requested_pages: list[tuple[int, int]] = []

    async def get_by_id(
        self, service_account_id: ServiceAccountId
    ) -> ServiceAccount | None:
        return self._accounts.get(service_account_id)

    async def get_by_id_with_lock(
        self, service_account_id: ServiceAccountId
    ) -> ServiceAccount | None:
        self.locked_ids.append(service_account_id)
        return self._accounts.get(service_account_id)

    async def get_by_client_id(self, client_id: ClientId) -> ServiceAccount | None:
        return next(
            (
                account
                for account in self._accounts.values()
                if account.client_id == client_id
            ),
            None,
        )

    async def list_page(self, *, limit: int, offset: int) -> list[ServiceAccount]:
        self.requested_pages.append((limit, offset))
        ordered = sorted(self._accounts.values(), key=lambda item: item.created_at)
        return ordered[offset : offset + limit]

    async def add(self, service_account: ServiceAccount) -> None:
        self._accounts[service_account.id] = service_account
        self.added.append(service_account)

    async def save(self, service_account: ServiceAccount) -> None:
        self.saved.append(service_account)

    async def save_last_used_at(self, service_account: ServiceAccount) -> None:
        self.usage_saved.append(service_account)


class ClientCredentialsStub:
    def __init__(self, secrets: Iterable[str] = ("plain-secret-new",)) -> None:
        self._secrets = list(secrets)
        self.issued: list[IssuedClientSecret] = []
        self.verified: list[tuple[str, ClientSecretHash]] = []

    def new_client_id(self) -> ClientId:
        return ClientId("sa_" + "n" * 32)

    def issue_secret(self) -> IssuedClientSecret:
        plain = self._secrets.pop(0)
        issued = IssuedClientSecret(plain_secret=plain, secret_hash=hash_of(plain))
        self.issued.append(issued)
        return issued

    def matches(self, plain_secret: str, secret_hash: ClientSecretHash) -> bool:
        self.verified.append((plain_secret, secret_hash))
        return hash_of(plain_secret) == secret_hash


class MachineTokenIssuerStub:
    def __init__(self, lifetime: timedelta = timedelta(minutes=15)) -> None:
        self._lifetime = lifetime
        self.calls: list[dict[str, object]] = []

    def issue(
        self,
        *,
        service_account_id: ServiceAccountId,
        client_id: ClientId,
        scopes: frozenset[MachineScope],
        issued_at: datetime,
    ) -> IssuedMachineToken:
        self.calls.append(
            {
                "service_account_id": service_account_id,
                "client_id": client_id,
                "scopes": scopes,
                "issued_at": issued_at,
            }
        )
        return IssuedMachineToken(
            plain_token="machine-token",
            expires_at=issued_at + self._lifetime,
        )
