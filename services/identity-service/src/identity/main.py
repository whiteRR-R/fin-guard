from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import timedelta

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.ports.clock import Clock
from identity.application.ports.security.access_token_issuer import AccessTokenIssuer
from identity.application.ports.security.access_token_verifier import (
    AccessTokenVerifier,
)
from identity.application.ports.security.invitation_token_issuer import (
    InvitationTokenIssuer,
)
from identity.application.ports.security.invitation_token_verifier import (
    InvitationTokenVerifier,
)
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.security.refresh_token_issuer import RefreshTokenIssuer
from identity.application.ports.security.refresh_token_verifier import (
    RefreshTokenVerifier,
)
from identity.presentation.api.dependencies.services import ApiServices
from identity.presentation.api.errors import install_error_handlers
from identity.presentation.api.v1.router import router as v1_router


def create_app(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    password_hasher: PasswordHasher,
    access_token_issuer: AccessTokenIssuer,
    access_token_verifier: AccessTokenVerifier,
    refresh_token_issuer: RefreshTokenIssuer,
    refresh_token_verifier: RefreshTokenVerifier,
    refresh_token_lifetime: timedelta,
    invitation_token_issuer: InvitationTokenIssuer,
    invitation_token_verifier: InvitationTokenVerifier,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    app = FastAPI(title="FinGuard Identity Service", lifespan=lifespan)
    install_error_handlers(app)
    app.state.identity_services = ApiServices(
        session_factory=session_factory,
        clock=clock,
        password_hasher=password_hasher,
        access_token_issuer=access_token_issuer,
        access_token_verifier=access_token_verifier,
        refresh_token_issuer=refresh_token_issuer,
        refresh_token_verifier=refresh_token_verifier,
        refresh_token_lifetime=refresh_token_lifetime,
        invitation_token_issuer=invitation_token_issuer,
        invitation_token_verifier=invitation_token_verifier,
    )
    app.include_router(v1_router)
    return app
