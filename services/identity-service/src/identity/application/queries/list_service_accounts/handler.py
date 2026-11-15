from identity.application.authorization import require_active_admin
from identity.application.exceptions import InvalidPaginationError
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.service_account_repository import (
    ServiceAccountRepository,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.application.queries.get_service_account.result import (
    ServiceAccountView,
)
from identity.application.queries.list_service_accounts.query import (
    ListServiceAccountsQuery,
)
from identity.application.queries.list_service_accounts.result import (
    ListServiceAccountsResult,
)
from identity.domain.value_objects.employee_id import EmployeeId


class ListServiceAccountsHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        employees: EmployeeRepository,
        service_accounts: ServiceAccountRepository,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._employees = employees
        self._service_accounts = service_accounts

    async def execute(
        self, query: ListServiceAccountsQuery
    ) -> ListServiceAccountsResult:
        if type(query.limit) is not int or not 1 <= query.limit <= 100:
            raise InvalidPaginationError("Limit must be an integer between 1 and 100")

        if type(query.offset) is not int or query.offset < 0:
            raise InvalidPaginationError("Offset must be a non-negative integer")

        actor_id = EmployeeId(query.actor_id)

        async with self._uow:
            await require_active_admin(
                self._employees, actor_id, action="view service accounts"
            )

            accounts = await self._service_accounts.list_page(
                limit=query.limit + 1,
                offset=query.offset,
            )
            now = self._clock.now()

            return ListServiceAccountsResult(
                service_accounts=tuple(
                    ServiceAccountView.from_aggregate(account, now)
                    for account in accounts[: query.limit]
                ),
                limit=query.limit,
                offset=query.offset,
                has_more=len(accounts) > query.limit,
            )
