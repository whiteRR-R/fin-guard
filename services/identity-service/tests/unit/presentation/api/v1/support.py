import asyncio
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.exceptions import InvalidRefreshTokenError
from identity.application.ports.security.access_token_issuer import IssuedAccessToken
from identity.application.ports.security.access_token_verifier import AccessTokenClaims
from identity.application.ports.security.refresh_token_issuer import IssuedRefreshToken
from identity.application.ports.security.refresh_token_verifier import (
    RefreshTokenClaims,
)
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import HashedPassword
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)
from identity.infrastructure.persistence.models.employee import EmployeeModel
from identity.infrastructure.persistence.models.session import SessionModel
from identity.infrastructure.persistence.models.used_refresh_token import (
    UsedRefreshTokenModel,
)
from identity.infrastructure.security.hmac_invitation_tokens import HmacInvitationTokens
from identity.main import create_app

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
EMPLOYEE_ID = EmployeeId(uuid4())
SESSION_ID = RefreshSessionId(uuid4())


class FixedClock:
    def now(self) -> datetime:
        return NOW


class AccessTokens:
    def verify(self, access_token: str) -> AccessTokenClaims:
        assert access_token == "valid-access-token"
        return AccessTokenClaims(
            employee_id=EMPLOYEE_ID,
            sid=SESSION_ID,
            roles=frozenset({EmployeeRole.ADMIN}),
            expires_at=NOW + timedelta(minutes=15),
        )

    def issue(
        self,
        employee_id: EmployeeId,
        session_id: RefreshSessionId,
        roles: frozenset[EmployeeRole],
        issued_at: datetime,
    ) -> IssuedAccessToken:
        return IssuedAccessToken(
            plain_token="issued-access-token",
            expires_at=NOW + timedelta(minutes=15),
        )


class RefreshTokens:
    def issue(self, session_id: RefreshSessionId) -> IssuedRefreshToken:
        return IssuedRefreshToken(
            plain_token="issued-refresh-token",
            token_hash=RefreshTokenHash("issued-refresh-token-hash"),
        )

    def verify(self, refresh_token: str) -> RefreshTokenClaims:
        if refresh_token not in {"valid-refresh-token", "issued-refresh-token"}:
            raise InvalidRefreshTokenError("Invalid refresh token")
        return RefreshTokenClaims(
            session_id=SESSION_ID,
            expires_at=NOW + timedelta(days=1),
        )

    def matches_hash(self, refresh_token: str, hashed_token: RefreshTokenHash) -> bool:
        return {
            "valid-refresh-token": "refresh-token-hash",
            "issued-refresh-token": "issued-refresh-token-hash",
        }.get(refresh_token) == hashed_token.value


class PasswordHasher:
    def verify(self, password, hashed_password) -> bool:
        return password.value == "valid-password-long"

    def hash(self, password) -> HashedPassword:
        return HashedPassword("new-password-hash")


class FakeSession:
    def __init__(self, roles: list[EmployeeRole]) -> None:
        self.employee = EmployeeModel(
            id=EMPLOYEE_ID.value,
            email="employee@example.com",
            roles=roles,
            password_hash="hashed-password",
            status=EmployeeStatus.ACTIVE,
        )
        self.refresh_session = SessionModel(
            id=SESSION_ID.value,
            employee_id=EMPLOYEE_ID.value,
            refresh_token_hash="refresh-token-hash",
            created_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=1),
            revoked_at=None,
        )
        self.added: list[object] = []
        self.commits = 0
        self.entries = 0

    async def __aenter__(self):
        self.entries += 1
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        pass

    async def scalar(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is EmployeeModel:
            return self.employee
        if model is SessionModel:
            return self.refresh_session
        return None

    async def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is UsedRefreshTokenModel:
            return [
                item.token_hash
                for item in self.added
                if isinstance(item, UsedRefreshTokenModel)
            ]
        if model is SessionModel:
            return [self.refresh_session]
        return [self.employee]

    async def execute(self, statement, params=None):
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def make_app(session: FakeSession):
    access_tokens = AccessTokens()
    refresh_tokens = RefreshTokens()
    invitation_tokens = HmacInvitationTokens(
        signing_key=b"test-invitation-signing-key-32-bytes",
        lifetime=timedelta(days=7),
    )
    return create_app(
        session_factory=cast(async_sessionmaker[AsyncSession], lambda: session),
        clock=FixedClock(),
        password_hasher=PasswordHasher(),
        access_token_issuer=access_tokens,
        access_token_verifier=access_tokens,
        refresh_token_issuer=refresh_tokens,
        refresh_token_verifier=refresh_tokens,
        refresh_token_lifetime=timedelta(days=30),
        invitation_token_issuer=invitation_tokens,
        invitation_token_verifier=invitation_tokens,
    )


def request(app, method: str, path: str, *, body=None, token=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    async def send_request():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.request(method, path, json=body, headers=headers)
            return response.status_code, response.json() if response.content else None

    return asyncio.run(send_request())
