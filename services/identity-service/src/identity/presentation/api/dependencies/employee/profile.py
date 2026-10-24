from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.commands.change_email.handler import ChangeEmailHandler
from identity.application.commands.change_password.handler import ChangePasswordHandler
from identity.application.queries.get_current_employee.handler import (
    GetCurrentEmployeeHandler,
)
from identity.infrastructure.persistence.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.infrastructure.persistence.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import (
    RepositoryDependencies,
)
from identity.presentation.api.dependencies.employee.types import (
    EmployeeApiServices,
    Provider,
)


@dataclass(frozen=True)
class ProfileDependencies:
    current_employee: Provider[GetCurrentEmployeeHandler]
    change_email: Provider[ChangeEmailHandler]
    change_password: Provider[ChangePasswordHandler]


def create_profile_dependencies(
    services: EmployeeApiServices,
    repositories: RepositoryDependencies,
) -> ProfileDependencies:
    async def get_current_employee_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
    ) -> GetCurrentEmployeeHandler:
        return GetCurrentEmployeeHandler(
            uow=SqlAlchemyUnitOfWork(session),
            employee_repository=employees,
        )

    async def get_change_email_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
    ) -> ChangeEmailHandler:
        return ChangeEmailHandler(
            uow=SqlAlchemyUnitOfWork(session),
            employees=employees,
            password_hasher=services.password_hasher,
        )

    async def get_change_password_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        refresh_sessions: Annotated[
            RefreshSessionRepository, Depends(repositories.refresh_sessions)
        ],
    ) -> ChangePasswordHandler:
        return ChangePasswordHandler(
            uow=SqlAlchemyUnitOfWork(session),
            employees=employees,
            refresh_sessions=refresh_sessions,
            clock=services.clock,
            password_hasher=services.password_hasher,
        )

    return ProfileDependencies(
        current_employee=get_current_employee_handler,
        change_email=get_change_email_handler,
        change_password=get_change_password_handler,
    )
