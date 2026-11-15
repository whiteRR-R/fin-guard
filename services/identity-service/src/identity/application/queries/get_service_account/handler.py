from identity.application.authorization import require_active_admin
from identity.application.exceptions import ServiceAccountNotFoundError
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.service_account_repository import (
    ServiceAccountRepository,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.application.queries.get_service_account.query import (
    GetServiceAccountQuery,
)
from identity.application.queries.get_service_account.result import (
    ServiceAccountView,
)
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.service_account import ServiceAccountId


class GetServiceAccountHandler:
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

    async def execute(self, query: GetServiceAccountQuery) -> ServiceAccountView:
        actor_id = EmployeeId(query.actor_id)
        service_account_id = ServiceAccountId(query.service_account_id)

        async with self._uow:
            await require_active_admin(
                self._employees, actor_id, action="view service accounts"
            )

            account = await self._service_accounts.get_by_id(service_account_id)

            if account is None:
                raise ServiceAccountNotFoundError("Service account not found")

            return ServiceAccountView.from_aggregate(account, self._clock.now())
