from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.commands.accept_invitation.handler import AcceptInvitationHandler
from identity.infrastructure.persistence.repositories.employee_repository import EmployeeRepository
from identity.infrastructure.persistence.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import RepositoryDependencies
from identity.presentation.api.dependencies.types import Provider
from identity.presentation.api.dependencies.invitation.types import InvitationApiServices


@dataclass(frozen=True)
class InvitationAcceptanceDependencies:
    accept: Provider[AcceptInvitationHandler]


def create_invitation_acceptance_dependencies(
    services: InvitationApiServices,
    repositories: RepositoryDependencies,
) -> InvitationAcceptanceDependencies:
    async def get_accept_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        invitations: Annotated[InvitationRepository, Depends(repositories.invitations)],
    ) -> AcceptInvitationHandler:
        return AcceptInvitationHandler(
            uow=SqlAlchemyUnitOfWork(session),
            clock=services.clock,
            employees=employees,
            invitations=invitations,
            password_hasher=services.password_hasher,
            invitation_verifier=services.token_verifier,
        )

    return InvitationAcceptanceDependencies(accept=get_accept_handler)
