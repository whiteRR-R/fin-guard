from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.infrastructure.persistence.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.infrastructure.persistence.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.infrastructure.persistence.repositories.outbox_repository import (
    OutboxRepository,
)
from identity.infrastructure.persistence.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.presentation.api.dependencies.types import Provider, SessionProvider


@dataclass(frozen=True)
class RepositoryDependencies:
    session: SessionProvider
    employees: Provider[EmployeeRepository]
    invitations: Provider[InvitationRepository]
    refresh_sessions: Provider[RefreshSessionRepository]
    outbox: Provider[OutboxRepository]


def create_repository_dependencies(
    session_factory: async_sessionmaker[AsyncSession],
) -> RepositoryDependencies:
    async def get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    async def get_employees(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> EmployeeRepository:
        return EmployeeRepository(session)

    async def get_invitations(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> InvitationRepository:
        return InvitationRepository(session)

    async def get_refresh_sessions(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> RefreshSessionRepository:
        return RefreshSessionRepository(session)

    async def get_outbox(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> OutboxRepository:
        return OutboxRepository(session)

    return RepositoryDependencies(
        session=get_session,
        employees=get_employees,
        invitations=get_invitations,
        refresh_sessions=get_refresh_sessions,
        outbox=get_outbox,
    )
