from datetime import timedelta

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.ports.clock import Clock
from identity.application.ports.security.access_token_issuer import AccessTokenIssuer
from identity.application.ports.security.access_token_verifier import AccessTokenVerifier
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.security.refresh_token_issuer import RefreshTokenIssuer
from identity.presentation.api.dependencies.employee.factory import (
    create_employee_dependencies,
)
from identity.presentation.api.dependencies.employee.types import EmployeeApiServices
from identity.presentation.api.errors import install_error_handlers
from identity.presentation.api.v1.router import create_v1_router


def create_app(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    password_hasher: PasswordHasher,
    access_token_issuer: AccessTokenIssuer,
    access_token_verifier: AccessTokenVerifier,
    refresh_token_issuer: RefreshTokenIssuer,
    refresh_token_lifetime: timedelta,
) -> FastAPI:
    app = FastAPI(title="FinGuard Identity Service")
    install_error_handlers(app)
    employee_dependencies = create_employee_dependencies(
        EmployeeApiServices(
            session_factory=session_factory,
            clock=clock,
            password_hasher=password_hasher,
            access_token_issuer=access_token_issuer,
            access_token_verifier=access_token_verifier,
            refresh_token_issuer=refresh_token_issuer,
            refresh_token_lifetime=refresh_token_lifetime,
        )
    )
    app.include_router(create_v1_router(employee_dependencies))
    return app
