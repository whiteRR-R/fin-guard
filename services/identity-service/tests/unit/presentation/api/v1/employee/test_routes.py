import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from identity.application.ports.security.access_token_issuer import IssuedAccessToken
from identity.application.ports.security.access_token_verifier import AccessTokenClaims
from identity.application.ports.security.refresh_token_issuer import IssuedRefreshToken
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

    def issue(self, **kwargs) -> IssuedAccessToken:
        return IssuedAccessToken(
            plain_token="issued-access-token",
            expires_at=NOW + timedelta(minutes=15),
        )


class RefreshTokens:
    def issue(self, session_id: RefreshSessionId) -> IssuedRefreshToken:
        return IssuedRefreshToken(
            plain_token="issued-refresh-token",
            token_hash=RefreshTokenHash("refresh-token-hash"),
        )


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
        if statement.column_descriptions[0]["entity"] is SessionModel:
            return [self.refresh_session]
        return [self.employee]

    async def execute(self, statement):
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def make_app(session: FakeSession):
    access_tokens = AccessTokens()
    return create_app(
        session_factory=lambda: session,
        clock=FixedClock(),
        password_hasher=PasswordHasher(),
        access_token_issuer=access_tokens,
        access_token_verifier=access_tokens,
        refresh_token_issuer=RefreshTokens(),
        refresh_token_lifetime=timedelta(days=30),
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


def test_current_employee_requires_access_token() -> None:
    status_code, body = request(
        make_app(FakeSession([EmployeeRole.ADMIN])),
        "GET",
        "/api/v1/employees/me",
    )
    assert status_code == 401
    assert body == {"detail": "Authentication required"}


def test_current_employee_returns_authenticated_employee() -> None:
    session = FakeSession([EmployeeRole.ADMIN])
    status_code, body = request(
        make_app(session),
        "GET",
        "/api/v1/employees/me",
        token="valid-access-token",
    )
    assert status_code == 200
    assert body["employee_id"] == str(EMPLOYEE_ID.value)
    assert body["email"] == "employee@example.com"
    assert body["roles"] == ["ADMIN"]
    assert session.entries == 1


def test_login_issues_tokens_and_commits_session() -> None:
    session = FakeSession([EmployeeRole.ADMIN])
    status_code, body = request(
        make_app(session),
        "POST",
        "/api/v1/auth/login",
        body={"email": "employee@example.com", "password": "valid-password-long"},
    )
    assert status_code == 200
    assert body["access_token"] == "issued-access-token"
    assert body["refresh_token"] == "issued-refresh-token"
    assert body["token_type"] == "bearer"
    assert session.commits == 1
    assert len(session.added) == 1
    assert session.entries == 1


def test_login_rejects_wrong_password_without_creating_session() -> None:
    session = FakeSession([EmployeeRole.ADMIN])
    status_code, body = request(
        make_app(session),
        "POST",
        "/api/v1/auth/login",
        body={"email": "employee@example.com", "password": "wrong-password-long"},
    )

    assert status_code == 401
    assert body == {"detail": "Invalid credentials"}
    assert session.commits == 0
    assert session.added == []


def test_list_employees_denies_employee_without_allowed_role() -> None:
    status_code, body = request(
        make_app(FakeSession([EmployeeRole.AUDITOR])),
        "GET",
        "/api/v1/employees",
        token="valid-access-token",
    )
    assert status_code == 403
    assert body == {"detail": "Access denied"}


def test_assign_role_commits_employee_and_outbox() -> None:
    session = FakeSession([EmployeeRole.ADMIN])
    status_code, body = request(
        make_app(session),
        "PUT",
        f"/api/v1/employees/{EMPLOYEE_ID.value}/roles/AUDITOR",
        token="valid-access-token",
    )
    assert status_code == 204
    assert body is None
    assert EmployeeRole.AUDITOR in session.employee.roles
    assert session.commits == 1
    assert len(session.added) == 1
    assert session.added[0].message_type == "EmployeeRoleAssigned"
    assert session.entries == 1


def test_change_password_revokes_sessions_and_commits() -> None:
    session = FakeSession([EmployeeRole.ADMIN])
    status_code, body = request(
        make_app(session),
        "PUT",
        "/api/v1/employees/me/password",
        body={
            "current_password": "valid-password-long",
            "new_password": "different-password-long",
        },
        token="valid-access-token",
    )
    assert status_code == 204
    assert body is None
    assert session.employee.password_hash == "new-password-hash"
    assert session.refresh_session.revoked_at == NOW
    assert session.commits == 1


def test_public_registration_route_is_absent() -> None:
    app = make_app(FakeSession([EmployeeRole.ADMIN]))
    paths = app.openapi()["paths"]
    assert "/register" not in paths
    assert "/api/v1/register" not in paths
    assert all(path.startswith("/api/v1/") for path in paths)
    assert "/api/v2/auth/login" not in paths
