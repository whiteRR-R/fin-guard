from identity.application.commands.create_service_account.handler import (
    CreateServiceAccountHandler,
)
from identity.application.commands.revoke_service_account.handler import (
    RevokeServiceAccountHandler,
)
from identity.application.commands.rotate_client_secret.handler import (
    RotateClientSecretHandler,
)
from identity.application.queries.get_service_account.handler import (
    GetServiceAccountHandler,
)
from identity.application.queries.list_service_accounts.handler import (
    ListServiceAccountsHandler,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import (
    AsyncSessionDependency,
    EmployeeRepositoryDependency,
    OutboxRepositoryDependency,
    ServiceAccountRepositoryDependency,
)
from identity.presentation.api.dependencies.services import (
    ClientCredentialsIssuerDependency,
    ClientSecretGracePeriodDependency,
    ClockDependency,
)


async def get_create_service_account_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    outbox: OutboxRepositoryDependency,
    employees: EmployeeRepositoryDependency,
    service_accounts: ServiceAccountRepositoryDependency,
    credentials: ClientCredentialsIssuerDependency,
) -> CreateServiceAccountHandler:
    return CreateServiceAccountHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        outbox=outbox,
        employees=employees,
        service_accounts=service_accounts,
        credentials=credentials,
    )


async def get_rotate_client_secret_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    outbox: OutboxRepositoryDependency,
    employees: EmployeeRepositoryDependency,
    service_accounts: ServiceAccountRepositoryDependency,
    credentials: ClientCredentialsIssuerDependency,
    grace_period: ClientSecretGracePeriodDependency,
) -> RotateClientSecretHandler:
    return RotateClientSecretHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        outbox=outbox,
        employees=employees,
        service_accounts=service_accounts,
        credentials=credentials,
        grace_period=grace_period,
    )


async def get_revoke_service_account_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    outbox: OutboxRepositoryDependency,
    employees: EmployeeRepositoryDependency,
    service_accounts: ServiceAccountRepositoryDependency,
) -> RevokeServiceAccountHandler:
    return RevokeServiceAccountHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        outbox=outbox,
        employees=employees,
        service_accounts=service_accounts,
    )


async def get_service_account_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    employees: EmployeeRepositoryDependency,
    service_accounts: ServiceAccountRepositoryDependency,
) -> GetServiceAccountHandler:
    return GetServiceAccountHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        employees=employees,
        service_accounts=service_accounts,
    )


async def get_list_service_accounts_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    employees: EmployeeRepositoryDependency,
    service_accounts: ServiceAccountRepositoryDependency,
) -> ListServiceAccountsHandler:
    return ListServiceAccountsHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        employees=employees,
        service_accounts=service_accounts,
    )
