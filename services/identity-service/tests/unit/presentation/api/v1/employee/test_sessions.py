from identity.domain.enums.role import EmployeeRole
from identity.infrastructure.persistence.models.outbox_message import OutboxMessageModel
from identity.infrastructure.persistence.models.used_refresh_token import (
    UsedRefreshTokenModel,
)
from tests.unit.presentation.api.v1.support import (
    NOW,
    SESSION_ID,
    FakeSession,
    make_app,
    request,
)


def test_refresh_rotates_token_and_commits_used_hash() -> None:
    session = FakeSession([EmployeeRole.ADMIN])

    status_code, body = request(
        make_app(session),
        "POST",
        "/api/v1/auth/refresh",
        body={"refresh_token": "valid-refresh-token"},
    )

    assert status_code == 200
    assert body == {
        "access_token": "issued-access-token",
        "refresh_token": "issued-refresh-token",
        "token_type": "bearer",
    }
    assert session.refresh_session.refresh_token_hash == "issued-refresh-token-hash"
    assert session.commits == 1
    assert session.entries == 1
    assert len(session.added) == 1
    assert isinstance(session.added[0], UsedRefreshTokenModel)
    assert session.added[0].token_hash == "refresh-token-hash"


def test_reused_refresh_token_revokes_session_and_records_event() -> None:
    session = FakeSession([EmployeeRole.ADMIN])
    app = make_app(session)
    first_status, _ = request(
        app,
        "POST",
        "/api/v1/auth/refresh",
        body={"refresh_token": "valid-refresh-token"},
    )

    second_status, body = request(
        app,
        "POST",
        "/api/v1/auth/refresh",
        body={"refresh_token": "valid-refresh-token"},
    )

    assert first_status == 200
    assert second_status == 401
    assert body == {"detail": "Invalid credentials"}
    assert session.refresh_session.revoked_at == NOW
    assert session.commits == 2
    events = [item for item in session.added if isinstance(item, OutboxMessageModel)]
    assert len(events) == 1
    assert events[0].message_type == "RefreshTokenReuseDetected"


def test_invalid_refresh_token_is_rejected_without_transaction() -> None:
    session = FakeSession([EmployeeRole.ADMIN])

    status_code, body = request(
        make_app(session),
        "POST",
        "/api/v1/auth/refresh",
        body={"refresh_token": "invalid"},
    )

    assert status_code == 401
    assert body == {"detail": "Invalid credentials"}
    assert session.entries == 1
    assert session.commits == 0


def test_logout_revokes_current_session_with_one_database_session() -> None:
    session = FakeSession([EmployeeRole.ADMIN])

    status_code, body = request(
        make_app(session),
        "POST",
        "/api/v1/auth/logout",
        token="valid-access-token",
    )

    assert status_code == 204
    assert body is None
    assert session.refresh_session.revoked_at == NOW
    assert session.commits == 1
    assert session.entries == 1
    assert isinstance(session.added[0], OutboxMessageModel)
    assert session.added[0].message_type == "SessionLoggedOut"


def test_logout_all_revokes_active_sessions() -> None:
    session = FakeSession([EmployeeRole.ADMIN])

    status_code, body = request(
        make_app(session),
        "POST",
        "/api/v1/auth/logout-all",
        token="valid-access-token",
    )

    assert status_code == 204
    assert body is None
    assert session.refresh_session.revoked_at == NOW
    assert session.commits == 1
    assert session.entries == 1
    assert isinstance(session.added[0], OutboxMessageModel)
    assert session.added[0].message_type == "AllSessionsLoggedOut"


def test_list_own_sessions_marks_current_session() -> None:
    session = FakeSession([EmployeeRole.ADMIN])

    status_code, body = request(
        make_app(session),
        "GET",
        "/api/v1/employees/me/sessions",
        token="valid-access-token",
    )

    assert status_code == 200
    assert body is not None
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["session_id"] == str(SESSION_ID.value)
    assert body["sessions"][0]["is_current"] is True
    assert session.entries == 1
    assert session.commits == 0


def test_revoke_own_session_revokes_target_and_records_event() -> None:
    session = FakeSession([EmployeeRole.ADMIN])

    status_code, body = request(
        make_app(session),
        "DELETE",
        f"/api/v1/employees/me/sessions/{SESSION_ID.value}",
        token="valid-access-token",
    )

    assert status_code == 204
    assert body is None
    assert session.refresh_session.revoked_at == NOW
    assert session.entries == 1
    assert session.commits == 1
    assert isinstance(session.added[0], OutboxMessageModel)
    assert session.added[0].message_type == "SessionRevoked"


def test_session_routes_require_access_token() -> None:
    app = make_app(FakeSession([EmployeeRole.ADMIN]))

    for method, path in (
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/auth/logout-all"),
        ("GET", "/api/v1/employees/me/sessions"),
        ("DELETE", f"/api/v1/employees/me/sessions/{SESSION_ID.value}"),
    ):
        status_code, body = request(app, method, path)
        assert status_code == 401
        assert body == {"detail": "Authentication required"}
