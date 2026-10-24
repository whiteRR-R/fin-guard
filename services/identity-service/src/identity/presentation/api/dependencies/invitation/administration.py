from identity.application.commands.invite_employee.handler import InviteEmployeeHandler
from identity.application.commands.reissue_invitation.handler import (
    ReissueInvitationHandler,
)
from identity.application.commands.revoke_invitation.handler import (
    RevokeInvitationHandler,
)
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import (
    AsyncSessionDependency,
    EmployeeRepositoryDependency,
    InvitationRepositoryDependency,
    OutboxRepositoryDependency,
)
from identity.presentation.api.dependencies.services import (
    ClockDependency,
    InvitationTokenIssuerDependency,
)


async def get_invite_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    invitations: InvitationRepositoryDependency,
    outbox: OutboxRepositoryDependency,
    clock: ClockDependency,
    invitation_token_issuer: InvitationTokenIssuerDependency,
) -> InviteEmployeeHandler:
    return InviteEmployeeHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        outbox=outbox,
        employees=employees,
        invitations=invitations,
        invite_policy=EmployeeInvitePolicy(),
        invitation_token_issuer=invitation_token_issuer,
    )


async def get_revoke_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    invitations: InvitationRepositoryDependency,
    outbox: OutboxRepositoryDependency,
    clock: ClockDependency,
) -> RevokeInvitationHandler:
    return RevokeInvitationHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        employees=employees,
        invitations=invitations,
        outbox=outbox,
    )


async def get_reissue_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    invitations: InvitationRepositoryDependency,
    outbox: OutboxRepositoryDependency,
    clock: ClockDependency,
    invitation_token_issuer: InvitationTokenIssuerDependency,
) -> ReissueInvitationHandler:
    return ReissueInvitationHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        outbox=outbox,
        employees=employees,
        invitations=invitations,
        invitation_policy=EmployeeInvitePolicy(),
        invitation_token_issuer=invitation_token_issuer,
    )
