from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.commands.invite_employee.handler import InviteEmployeeHandler
from identity.application.commands.reissue_invitation.handler import ReissueInvitationHandler
from identity.application.commands.revoke_invitation.handler import RevokeInvitationHandler
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.infrastructure.persistence.repositories.employee_repository import EmployeeRepository
from identity.infrastructure.persistence.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.infrastructure.persistence.repositories.outbox_repository import OutboxRepository
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import RepositoryDependencies
from identity.presentation.api.dependencies.types import Provider
from identity.presentation.api.dependencies.invitation.types import InvitationApiServices


@dataclass(frozen=True)
class InvitationAdministrationDependencies:
    invite: Provider[InviteEmployeeHandler]
    revoke: Provider[RevokeInvitationHandler]
    reissue: Provider[ReissueInvitationHandler]


def create_invitation_administration_dependencies(
    services: InvitationApiServices,
    repositories: RepositoryDependencies,
) -> InvitationAdministrationDependencies:
    async def get_invite_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        invitations: Annotated[InvitationRepository, Depends(repositories.invitations)],
        outbox: Annotated[OutboxRepository, Depends(repositories.outbox)],
    ) -> InviteEmployeeHandler:
        return InviteEmployeeHandler(
            uow=SqlAlchemyUnitOfWork(session),
            clock=services.clock,
            outbox=outbox,
            employees=employees,
            invitations=invitations,
            invite_policy=EmployeeInvitePolicy(),
            invitation_token_issuer=services.token_issuer,
        )

    async def get_revoke_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        invitations: Annotated[InvitationRepository, Depends(repositories.invitations)],
        outbox: Annotated[OutboxRepository, Depends(repositories.outbox)],
    ) -> RevokeInvitationHandler:
        return RevokeInvitationHandler(
            uow=SqlAlchemyUnitOfWork(session),
            clock=services.clock,
            employees=employees,
            invitations=invitations,
            outbox=outbox,
        )

    async def get_reissue_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        invitations: Annotated[InvitationRepository, Depends(repositories.invitations)],
        outbox: Annotated[OutboxRepository, Depends(repositories.outbox)],
    ) -> ReissueInvitationHandler:
        return ReissueInvitationHandler(
            uow=SqlAlchemyUnitOfWork(session),
            clock=services.clock,
            outbox=outbox,
            employees=employees,
            invitations=invitations,
            invitation_policy=EmployeeInvitePolicy(),
            invitation_token_issuer=services.token_issuer,
        )

    return InvitationAdministrationDependencies(
        invite=get_invite_handler,
        revoke=get_revoke_handler,
        reissue=get_reissue_handler,
    )
