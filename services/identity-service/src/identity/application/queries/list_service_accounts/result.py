from dataclasses import dataclass

from identity.application.queries.get_service_account.result import (
    ServiceAccountView,
)


@dataclass(frozen=True, slots=True)
class ListServiceAccountsResult:
    service_accounts: tuple[ServiceAccountView, ...]
    limit: int
    offset: int
    has_more: bool
