from identity.application.authorization import require_active_admin
from identity.application.commands.create_service_account.command import (
    CreateServiceAccountCommand,
)
from identity.application.commands.create_service_account.result import (
    CreateServiceAccountResult,
)
from identity.application.messages.service_account_created import (
    ServiceAccountCreatedMessage,
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
from identity.domain.aggregates.service_account import ServiceAccount
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.service_account import (
    ClientSecretId,
    ServiceAccountId,
    ServiceAccountName,
)


class CreateServiceAccountHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        outbox: OutboxRepository,
        employees: EmployeeRepository,
        service_accounts: ServiceAccountRepository,
        credentials: ClientCredentialsIssuer,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._outbox = outbox
        self._employees = employees
        self._service_accounts = service_accounts
        self._credentials = credentials

    async def execute(
        self, command: CreateServiceAccountCommand
    ) -> CreateServiceAccountResult:
        actor_id = EmployeeId(command.actor_id)
        name = ServiceAccountName(command.name)

        async with self._uow:
            actor = await require_active_admin(
                self._employees, actor_id, action="create service accounts"
            )

            now = self._clock.now()
            client_id = self._credentials.new_client_id()
            secret = self._credentials.issue_secret()
            account = ServiceAccount.create(
                service_account_id=ServiceAccountId.new(),
                client_id=client_id,
                name=name,
                scopes=command.scopes,
                created_by=actor.id,
                secret_id=ClientSecretId.new(),
                secret_hash=secret.secret_hash,
                created_at=now,
            )
            scopes = tuple(sorted(account.scopes, key=lambda scope: scope.value))

            await self._service_accounts.add(account)
            await self._outbox.add(
                ServiceAccountCreatedMessage(
                    service_account_id=account.id.value,
                    client_id=account.client_id.value,
                    actor_id=actor.id.value,
                    scopes=scopes,
                    created_at=now,
                )
            )
            await self._uow.commit()

        return CreateServiceAccountResult(
            service_account_id=account.id.value,
            client_id=account.client_id.value,
            client_secret=secret.plain_secret,
            scopes=scopes,
            created_at=account.created_at,
        )
