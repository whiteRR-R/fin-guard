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
from identity.infrastructure.rate_limit.limits import RateLimit, RateLimitExceededError
from identity.infrastructure.security.hmac_client_credentials import (
    HmacClientCredentials,
)
from identity.infrastructure.security.hmac_invitation_tokens import HmacInvitationTokens
from identity.infrastructure.security.jwt_machine_tokens import JwtMachineTokens
from identity.main import create_app
from identity.presentation.api.rate_limit import AuthenticationRateLimits

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
EMPLOYEE_ID = EmployeeId(uuid4())
SESSION_ID = RefreshSessionId(uuid4())
CLIENT_SECRET_HASH_KEY = b"test-client-secret-hash-key-32-bytes"
MACHINE_SIGNING_KEY = b"test-machine-token-signing-key-32b"


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


class InMemoryRateLimiter:
    def __init__(self, clock=None) -> None:
        self._clock = clock or FixedClock()
        self.hits: dict[tuple[str, str, object], int] = {}

    def _key(self, rate_limit: RateLimit, subject: str):
        now = self._clock.now()
        return (rate_limit.name, subject, rate_limit.window_start(now))

    async def ensure_allowed(self, *checks: tuple[RateLimit, str]) -> None:
        now = self._clock.now()
        for rate_limit, subject in checks:
            if self.hits.get(self._key(rate_limit, subject), 0) >= rate_limit.limit:
                raise RateLimitExceededError(rate_limit.retry_after(now))

    async def record(self, *hits: tuple[RateLimit, str]) -> None:
        for rate_limit, subject in hits:
            key = self._key(rate_limit, subject)
            self.hits[key] = self.hits.get(key, 0) + 1

    def count(self, name: str, subject: str) -> int:
        return sum(
            value
            for (key_name, key_subject, _), value in self.hits.items()
            if key_name == name and key_subject == subject
        )


TEST_RATE_LIMITS = AuthenticationRateLimits(
    login_per_ip=RateLimit("login:ip", 1000, timedelta(minutes=5)),
    login_failures_per_email=RateLimit("login:email", 1000, timedelta(minutes=15)),
    token_per_ip=RateLimit("token:ip", 1000, timedelta(minutes=1)),
    token_failures_per_client=RateLimit("token:client", 1000, timedelta(minutes=5)),
)


def make_app(
    session: FakeSession,
    *,
    rate_limiter: InMemoryRateLimiter | None = None,
    rate_limits: AuthenticationRateLimits = TEST_RATE_LIMITS,
):
    access_tokens = AccessTokens()
    refresh_tokens = RefreshTokens()
    client_credentials = HmacClientCredentials(CLIENT_SECRET_HASH_KEY)
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
        client_credentials_issuer=client_credentials,
        client_secret_verifier=client_credentials,
        machine_token_issuer=JwtMachineTokens(
            signing_key=MACHINE_SIGNING_KEY,
            lifetime=timedelta(minutes=15),
            issuer="identity-service",
            audience="finguard-api",
            clock=FixedClock(),
        ),
        client_secret_grace_period=timedelta(hours=24),
        rate_limiter=rate_limiter or InMemoryRateLimiter(),
        rate_limits=rate_limits,
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
