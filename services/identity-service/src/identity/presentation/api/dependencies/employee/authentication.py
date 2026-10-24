from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from identity.application.authentication.authenticate_access_token import (
    AuthenticateAccessToken,
    CurrentActor,
)
from identity.application.commands.login_employee.handler import LoginEmployeeHandler
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import (
    AsyncSessionDependency,
    EmployeeRepositoryDependency,
    RefreshSessionRepositoryDependency,
)
from identity.presentation.api.dependencies.services import (
    AccessTokenIssuerDependency,
    AccessTokenVerifierDependency,
    ClockDependency,
    PasswordHasherDependency,
    RefreshTokenIssuerDependency,
    RefreshTokenLifetimeDependency,
)

bearer = HTTPBearer(auto_error=False)


async def get_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    refresh_sessions: RefreshSessionRepositoryDependency,
    clock: ClockDependency,
    access_token_verifier: AccessTokenVerifierDependency,
) -> CurrentActor:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    authenticate = AuthenticateAccessToken(
        clock=clock,
        uow=SqlAlchemyUnitOfWork(session),
        employees=employees,
        refresh_sessions=refresh_sessions,
        access_token_verifier=access_token_verifier,
    )
    return await authenticate.execute(credentials.credentials)


async def get_login_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    refresh_sessions: RefreshSessionRepositoryDependency,
    clock: ClockDependency,
    password_hasher: PasswordHasherDependency,
    access_token_issuer: AccessTokenIssuerDependency,
    refresh_token_issuer: RefreshTokenIssuerDependency,
    refresh_token_lifetime: RefreshTokenLifetimeDependency,
) -> LoginEmployeeHandler:
    return LoginEmployeeHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        employees=employees,
        refresh_sessions=refresh_sessions,
        password_hasher=password_hasher,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
        refresh_token_lifetime=refresh_token_lifetime,
    )
