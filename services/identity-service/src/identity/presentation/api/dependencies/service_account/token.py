from identity.application.commands.issue_machine_access_token.handler import (
    IssueMachineAccessTokenHandler,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import (
    AsyncSessionDependency,
    ServiceAccountRepositoryDependency,
)
from identity.presentation.api.dependencies.services import (
    ClientSecretVerifierDependency,
    ClockDependency,
    MachineTokenIssuerDependency,
)


async def get_issue_machine_access_token_handler(
    session: AsyncSessionDependency,
    clock: ClockDependency,
    service_accounts: ServiceAccountRepositoryDependency,
    secret_verifier: ClientSecretVerifierDependency,
    token_issuer: MachineTokenIssuerDependency,
) -> IssueMachineAccessTokenHandler:
    return IssueMachineAccessTokenHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        service_accounts=service_accounts,
        secret_verifier=secret_verifier,
        token_issuer=token_issuer,
    )
