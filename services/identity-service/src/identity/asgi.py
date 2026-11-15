from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import cast

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from identity.infrastructure.clock import SystemClock
from identity.infrastructure.config import (
    ServiceAccountSettings,
    TokenSettings,
    get_database_settings,
)
from identity.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from identity.infrastructure.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)
from identity.infrastructure.security.hmac_client_credentials import (
    HmacClientCredentials,
)
from identity.infrastructure.security.hmac_invitation_tokens import (
    HmacInvitationTokens,
)
from identity.infrastructure.security.jwt_access_tokens import JwtAccessTokens
from identity.infrastructure.security.jwt_machine_tokens import JwtMachineTokens
from identity.infrastructure.security.jwt_refresh_tokens import JwtRefreshTokens
from identity.main import create_app


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = cast(AsyncEngine, app.state.identity_engine)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        yield
    finally:
        await engine.dispose()


def create_application() -> FastAPI:
    database_settings = get_database_settings()
    token_settings = TokenSettings()
    service_account_settings = ServiceAccountSettings()
    clock = SystemClock()
    access_lifetime = timedelta(seconds=token_settings.access_token_lifetime_seconds)
    refresh_lifetime = timedelta(days=token_settings.refresh_token_lifetime_days)
    invitation_lifetime = timedelta(days=token_settings.invitation_token_lifetime_days)

    access_tokens = JwtAccessTokens(
        signing_key=token_settings.access_token_signing_key.get_secret_value().encode(
            "utf-8"
        ),
        lifetime=access_lifetime,
        issuer=token_settings.token_issuer,
        audience=token_settings.token_audience,
    )
    refresh_tokens = JwtRefreshTokens(
        signing_key=token_settings.refresh_token_signing_key.get_secret_value().encode(
            "utf-8"
        ),
        lifetime=refresh_lifetime,
        issuer=token_settings.token_issuer,
        audience=token_settings.token_audience,
        clock=clock,
    )
    invitation_tokens = HmacInvitationTokens(
        signing_key=token_settings.invitation_signing_key.get_secret_value().encode(
            "utf-8"
        ),
        lifetime=invitation_lifetime,
    )

    client_credentials = HmacClientCredentials(
        hash_key=service_account_settings.client_secret_hash_key.get_secret_value().encode(
            "utf-8"
        )
    )
    machine_tokens = JwtMachineTokens(
        signing_key=token_settings.access_token_signing_key.get_secret_value().encode(
            "utf-8"
        ),
        lifetime=timedelta(
            seconds=service_account_settings.machine_token_lifetime_seconds
        ),
        issuer=token_settings.token_issuer,
        audience=token_settings.token_audience,
        clock=clock,
    )

    engine = create_database_engine(database_settings)
    session_factory = create_session_factory(engine)
    app = create_app(
        session_factory=session_factory,
        clock=clock,
        password_hasher=BcryptPasswordHasher(),
        access_token_issuer=access_tokens,
        access_token_verifier=access_tokens,
        refresh_token_issuer=refresh_tokens,
        refresh_token_verifier=refresh_tokens,
        refresh_token_lifetime=refresh_lifetime,
        invitation_token_issuer=invitation_tokens,
        invitation_token_verifier=invitation_tokens,
        client_credentials_issuer=client_credentials,
        client_secret_verifier=client_credentials,
        machine_token_issuer=machine_tokens,
        client_secret_grace_period=timedelta(
            hours=service_account_settings.client_secret_rotation_grace_hours
        ),
        lifespan=lifespan,
    )
    app.state.identity_engine = engine
    return app
