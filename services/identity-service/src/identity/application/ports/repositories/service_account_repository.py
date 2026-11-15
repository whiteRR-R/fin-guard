from typing import Protocol

from identity.domain.aggregates.service_account import ServiceAccount
from identity.domain.value_objects.service_account import ClientId, ServiceAccountId


class ServiceAccountRepository(Protocol):
    async def get_by_id(
        self, service_account_id: ServiceAccountId
    ) -> ServiceAccount | None: ...

    async def get_by_id_with_lock(
        self, service_account_id: ServiceAccountId
    ) -> ServiceAccount | None: ...

    async def get_by_client_id(self, client_id: ClientId) -> ServiceAccount | None: ...

    async def list_page(self, *, limit: int, offset: int) -> list[ServiceAccount]: ...

    async def add(self, service_account: ServiceAccount) -> None: ...

    async def save(self, service_account: ServiceAccount) -> None: ...

    async def save_last_used_at(self, service_account: ServiceAccount) -> None: ...
