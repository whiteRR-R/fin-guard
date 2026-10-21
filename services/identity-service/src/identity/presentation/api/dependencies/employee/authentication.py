from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.authentication.authenticate_access_token import (
    AuthenticateAccessToken,
    CurrentActor,
)
from identity.application.commands.login_employee.handler import LoginEmployeeHandler
from identity.infrastructure.persistence.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.infrastructure.persistence.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.employee.repositories import (
    RepositoryDependencies,
)
from identity.presentation.api.dependencies.employee.types import (
    EmployeeApiServices,
    Provider,
)


@dataclass(frozen=True)
class AuthenticationDependencies:
    actor: Provider[CurrentActor]
    login: Provider[LoginEmployeeHandler]


def create_authentication_dependencies(
    services: EmployeeApiServices,
    repositories: RepositoryDependencies,
) -> AuthenticationDependencies:
    bearer = HTTPBearer(auto_error=False)

    async def get_actor(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(bearer)
        ],
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        refresh_sessions: Annotated[
            RefreshSessionRepository, Depends(repositories.refresh_sessions)
        ],
    ) -> CurrentActor:
        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        authenticate = AuthenticateAccessToken(
            clock=services.clock,
            uow=SqlAlchemyUnitOfWork(session),
            employees=employees,
            refresh_sessions=refresh_sessions,
            access_token_verifier=services.access_token_verifier,
        )
        return await authenticate.execute(credentials.credentials)

    async def get_login_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        refresh_sessions: Annotated[
            RefreshSessionRepository, Depends(repositories.refresh_sessions)
        ],
    ) -> LoginEmployeeHandler:
        return LoginEmployeeHandler(
            uow=SqlAlchemyUnitOfWork(session),
            clock=services.clock,
            employees=employees,
            refresh_sessions=refresh_sessions,
            password_hasher=services.password_hasher,
            access_token_issuer=services.access_token_issuer,
            refresh_token_issuer=services.refresh_token_issuer,
            refresh_token_lifetime=services.refresh_token_lifetime,
        )

    return AuthenticationDependencies(actor=get_actor, login=get_login_handler)
