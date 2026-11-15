from identity.application.authorization import require_active_admin
from identity.application.commands.revoke_service_account.command import (
    RevokeServiceAccountCommand,
)
from identity.application.exceptions import ServiceAccountNotFoundError
from identity.application.messages.service_account_revoked import (
    ServiceAccountRevokedMessage,
)
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.repositories.service_account_repository import (
    ServiceAccountRepository,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.service_account import ServiceAccountId


class RevokeServiceAccountHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        outbox: OutboxRepository,
        employees: EmployeeRepository,
        service_accounts: ServiceAccountRepository,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._outbox = outbox
        self._employees = employees
        self._service_accounts = service_accounts

    async def execute(self, command: RevokeServiceAccountCommand) -> None:
        actor_id = EmployeeId(command.actor_id)
        service_account_id = ServiceAccountId(command.service_account_id)

        async with self._uow:
            actor = await require_active_admin(
                self._employees, actor_id, action="revoke service accounts"
            )

            account = await self._service_accounts.get_by_id_with_lock(
                service_account_id
            )

            if account is None:
                raise ServiceAccountNotFoundError("Service account not found")

            now = self._clock.now()
            account.revoke(now)

            await self._service_accounts.save(account)
            await self._outbox.add(
                ServiceAccountRevokedMessage(
                    service_account_id=account.id.value,
                    actor_id=actor.id.value,
                    created_at=now,
                )
            )
            await self._uow.commit()
