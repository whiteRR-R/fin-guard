from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
from identity.presentation.api.dependencies.services import (
    AsyncSessionFactoryDependency,
)


async def get_session(
    factory: AsyncSessionFactoryDependency,
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session


AsyncSessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def get_employee_repository(
    session: AsyncSessionDependency,
) -> EmployeeRepository:
    return EmployeeRepository(session)


async def get_invitation_repository(
    session: AsyncSessionDependency,
) -> InvitationRepository:
    return InvitationRepository(session)


async def get_refresh_session_repository(
    session: AsyncSessionDependency,
) -> RefreshSessionRepository:
    return RefreshSessionRepository(session)


async def get_outbox_repository(session: AsyncSessionDependency) -> OutboxRepository:
    return OutboxRepository(session)


EmployeeRepositoryDependency = Annotated[
    EmployeeRepository, Depends(get_employee_repository)
]
InvitationRepositoryDependency = Annotated[
    InvitationRepository, Depends(get_invitation_repository)
]
RefreshSessionRepositoryDependency = Annotated[
    RefreshSessionRepository, Depends(get_refresh_session_repository)
]
OutboxRepositoryDependency = Annotated[OutboxRepository, Depends(get_outbox_repository)]
