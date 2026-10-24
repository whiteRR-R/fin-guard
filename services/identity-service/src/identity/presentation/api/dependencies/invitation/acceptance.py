from identity.application.commands.accept_invitation.handler import (
    AcceptInvitationHandler,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import (
    AsyncSessionDependency,
    EmployeeRepositoryDependency,
    InvitationRepositoryDependency,
)
from identity.presentation.api.dependencies.services import (
    ClockDependency,
    InvitationTokenVerifierDependency,
    PasswordHasherDependency,
)


async def get_accept_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    invitations: InvitationRepositoryDependency,
    clock: ClockDependency,
    password_hasher: PasswordHasherDependency,
    invitation_verifier: InvitationTokenVerifierDependency,
) -> AcceptInvitationHandler:
    return AcceptInvitationHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        employees=employees,
        invitations=invitations,
        password_hasher=password_hasher,
        invitation_verifier=invitation_verifier,
    )
