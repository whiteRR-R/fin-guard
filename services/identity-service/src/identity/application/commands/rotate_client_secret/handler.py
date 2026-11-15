from datetime import timedelta

from identity.application.authorization import require_active_admin
from identity.application.commands.rotate_client_secret.command import (
    RotateClientSecretCommand,
)
from identity.application.commands.rotate_client_secret.result import (
    RotateClientSecretResult,
)
from identity.application.exceptions import ServiceAccountNotFoundError
from identity.application.messages.client_secret_rotated import (
    ClientSecretRotatedMessage,
)
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.repositories.service_account_repository import (
    ServiceAccountRepository,
)
from identity.application.ports.security.client_credentials import (
    ClientCredentialsIssuer,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.service_account import (
    ClientSecretId,
    ServiceAccountId,
)


class RotateClientSecretHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        outbox: OutboxRepository,
        employees: EmployeeRepository,
        service_accounts: ServiceAccountRepository,
        credentials: ClientCredentialsIssuer,
        grace_period: timedelta,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._outbox = outbox
        self._employees = employees
        self._service_accounts = service_accounts
        self._credentials = credentials
        self._grace_period = grace_period

    async def execute(
        self, command: RotateClientSecretCommand
    ) -> RotateClientSecretResult:
        actor_id = EmployeeId(command.actor_id)
        service_account_id = ServiceAccountId(command.service_account_id)

        async with self._uow:
            actor = await require_active_admin(
                self._employees, actor_id, action="rotate client secrets"
            )

            account = await self._service_accounts.get_by_id_with_lock(
                service_account_id
            )

            if account is None:
                raise ServiceAccountNotFoundError("Service account not found")

            now = self._clock.now()
            secret = self._credentials.issue_secret()
            previous = account.rotate_secret(
                secret_id=ClientSecretId.new(),
                secret_hash=secret.secret_hash,
                now=now,
                grace_period=self._grace_period,
            )
            previous_expires_at = previous.expires_at if previous else None

            await self._service_accounts.save(account)
            await self._outbox.add(
                ClientSecretRotatedMessage(
                    service_account_id=account.id.value,
                    actor_id=actor.id.value,
                    previous_secret_expires_at=previous_expires_at,
                    created_at=now,
                )
            )
            await self._uow.commit()

        return RotateClientSecretResult(
            service_account_id=account.id.value,
            client_id=account.client_id.value,
            client_secret=secret.plain_secret,
            previous_secret_expires_at=previous_expires_at,
        )
