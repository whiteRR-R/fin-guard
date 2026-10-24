import asyncio
from typing import cast

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import TextClause

from identity import asgi
from identity.infrastructure.config import DatabaseSettings
from identity.infrastructure.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)
from identity.infrastructure.security.hmac_invitation_tokens import (
    HmacInvitationTokens,
)
from identity.infrastructure.security.jwt_access_tokens import JwtAccessTokens
from identity.infrastructure.security.jwt_refresh_tokens import JwtRefreshTokens
from identity.presentation.api.dependencies.services import ApiServices


def _set_token_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCESS_TOKEN_SIGNING_KEY", "a" * 32)
    monkeypatch.setenv("REFRESH_TOKEN_SIGNING_KEY", "b" * 32)
    monkeypatch.setenv("INVITATION_SIGNING_KEY", "c" * 32)
    monkeypatch.setenv("TOKEN_ISSUER", "identity-service")
    monkeypatch.setenv("TOKEN_AUDIENCE", "finguard-api")


def test_create_application_wires_real_adapters_and_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_token_environment(monkeypatch)
    monkeypatch.setattr(
        asgi,
        "get_database_settings",
        lambda: DatabaseSettings(
            database_url=SecretStr(
                "postgresql+asyncpg://user:secret@localhost/identity"
            )
        ),
    )

    app = asgi.create_application()
    services = cast(ApiServices, app.state.identity_services)

    assert isinstance(services.password_hasher, BcryptPasswordHasher)
    assert isinstance(services.access_token_issuer, JwtAccessTokens)
    assert services.access_token_issuer is services.access_token_verifier
    assert isinstance(services.refresh_token_issuer, JwtRefreshTokens)
    assert isinstance(services.invitation_token_issuer, HmacInvitationTokens)
    assert services.invitation_token_issuer is services.invitation_token_verifier
    assert "/api/v1/auth/login" in app.openapi()["paths"]

    asyncio.run(cast(AsyncEngine, app.state.identity_engine).dispose())


def test_create_application_rejects_short_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_token_environment(monkeypatch)
    monkeypatch.setenv("ACCESS_TOKEN_SIGNING_KEY", "short")
    monkeypatch.setattr(
        asgi,
        "get_database_settings",
        lambda: DatabaseSettings(
            database_url=SecretStr(
                "postgresql+asyncpg://user:secret@localhost/identity"
            )
        ),
    )

    with pytest.raises(ValueError, match="Access token signing key"):
        asgi.create_application()


def test_lifespan_checks_database_and_disposes_engine() -> None:
    statements: list[str] = []

    class FakeConnection:
        async def __aenter__(self) -> "FakeConnection":  # noqa: PYI034
            return self

        async def __aexit__(self, exc_type, exc_value, traceback) -> None:
            pass

        async def execute(self, statement: TextClause) -> None:
            statements.append(str(statement))

    class FakeEngine:
        def __init__(self) -> None:
            self.disposals = 0

        def connect(self) -> FakeConnection:
            return FakeConnection()

        async def dispose(self) -> None:
            self.disposals += 1

    engine = FakeEngine()
    app = FastAPI()
    app.state.identity_engine = engine

    async def run() -> None:
        async with asgi.lifespan(app):
            assert engine.disposals == 0

    asyncio.run(run())

    assert statements == ["SELECT 1"]
    assert engine.disposals == 1


def test_lifespan_disposes_engine_when_database_is_unavailable() -> None:
    class FailingEngine:
        def __init__(self) -> None:
            self.disposals = 0

        def connect(self) -> None:
            raise RuntimeError("Database unavailable")

        async def dispose(self) -> None:
            self.disposals += 1

    engine = FailingEngine()
    app = FastAPI()
    app.state.identity_engine = engine

    async def run() -> None:
        async with asgi.lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="Database unavailable"):
        asyncio.run(run())

    assert engine.disposals == 1
