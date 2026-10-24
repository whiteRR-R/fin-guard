from identity.domain.enums.role import EmployeeRole
from tests.unit.presentation.api.v1.support import (
    EMPLOYEE_ID,
    NOW,
    FakeSession,
    make_app,
    request,
)


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
