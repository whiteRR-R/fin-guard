from datetime import timedelta
from uuid import UUID, uuid4

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.domain.value_objects.invitation_id import InvitationId
from identity.infrastructure.security.hmac_invitation_tokens import HmacInvitationTokens
from tests.unit.presentation.api.v1.invitation.support import InvitationSession
from tests.unit.presentation.api.v1.support import NOW, make_app, request


def test_invitation_routes_require_authentication_for_administration() -> None:
    app = make_app(InvitationSession([EmployeeRole.ADMIN]))
    invitation_id = uuid4()

    for method, path, body in (
        ("POST", "/api/v1/invitations", {"email": "new@example.com", "roles": ["AUDITOR"]}),
        ("POST", "/api/v1/invitations/reissue", {"email": "new@example.com"}),
        ("DELETE", f"/api/v1/invitations/{invitation_id}", None),
    ):
        status_code, response = request(app, method, path, body=body)
        assert status_code == 401
        assert response == {"detail": "Authentication required"}


def test_invite_employee_creates_invitation_without_exposing_token() -> None:
    session = InvitationSession([EmployeeRole.ADMIN])
    status_code, body = request(
        make_app(session),
        "POST",
        "/api/v1/invitations",
        body={"email": "new@example.com", "roles": ["AUDITOR"]},
        token="valid-access-token",
    )

    assert status_code == 201
    assert body is not None
    assert session.invited_employee is not None
    assert UUID(body["invitation_id"]) == session.invitations[0].id
    assert UUID(body["employee_id"]) == session.invited_employee.id
    assert set(body) == {"invitation_id", "employee_id"}
    assert session.invited_employee.status is EmployeeStatus.INVITED
    assert session.invitations[0].status is InvitationStatus.PENDING
    assert session.commits == 1


def test_invite_employee_rejects_non_admin_and_empty_roles() -> None:
    session = InvitationSession([EmployeeRole.AUDITOR])
    app = make_app(session)
    status_code, _ = request(
        app,
        "POST",
        "/api/v1/invitations",
        body={"email": "new@example.com", "roles": ["AUDITOR"]},
        token="valid-access-token",
    )
    assert status_code == 403
    assert session.commits == 0

    status_code, _ = request(
        app,
        "POST",
        "/api/v1/invitations",
        body={"email": "new@example.com", "roles": []},
        token="valid-access-token",
    )
    assert status_code == 422


def test_accept_invitation_activates_employee_without_authentication() -> None:
    session = InvitationSession([EmployeeRole.ADMIN])
    app = make_app(session)
    _, issued = request(
        app,
        "POST",
        "/api/v1/invitations",
        body={"email": "new@example.com", "roles": ["AUDITOR"]},
        token="valid-access-token",
    )
    assert issued is not None
    assert session.invited_employee is not None
    invitation_tokens = HmacInvitationTokens(
        signing_key=b"test-invitation-signing-key-32-bytes",
        lifetime=timedelta(days=7),
    )
    plain_token = invitation_tokens.derive_token(
        InvitationId(UUID(issued["invitation_id"]))
    )

    status_code, body = request(
        app,
        "POST",
        "/api/v1/invitations/accept",
        body={"token": plain_token, "password": "valid-password-long"},
    )
    assert status_code == 204
    assert body is None
    assert session.invited_employee.status is EmployeeStatus.ACTIVE
    assert session.invitations[0].status is InvitationStatus.ACCEPTED
    assert session.commits == 2

    status_code, _ = request(
        app,
        "POST",
        "/api/v1/invitations/accept",
        body={"token": plain_token, "password": "valid-password-long"},
    )
    assert status_code == 409
    assert session.commits == 2


def test_accept_invitation_rejects_invalid_token() -> None:
    status_code, body = request(
        make_app(InvitationSession([EmployeeRole.ADMIN])),
        "POST",
        "/api/v1/invitations/accept",
        body={"token": "invalid", "password": "valid-password-long"},
    )
    assert status_code == 400
    assert body == {"detail": "Invalid invitation token"}


def test_accept_invitation_reports_expired_token() -> None:
    session = InvitationSession([EmployeeRole.ADMIN])
    app = make_app(session)
    _, issued = request(
        app,
        "POST",
        "/api/v1/invitations",
        body={"email": "new@example.com", "roles": ["AUDITOR"]},
        token="valid-access-token",
    )
    assert issued is not None
    assert session.invited_employee is not None
    session.invitations[0].created_at = NOW - timedelta(days=8)
    session.invitations[0].expires_at = NOW - timedelta(days=1)
    invitation_tokens = HmacInvitationTokens(
        signing_key=b"test-invitation-signing-key-32-bytes",
        lifetime=timedelta(days=7),
    )
    plain_token = invitation_tokens.derive_token(
        InvitationId(UUID(issued["invitation_id"]))
    )

    status_code, body = request(
        app,
        "POST",
        "/api/v1/invitations/accept",
        body={"token": plain_token, "password": "valid-password-long"},
    )
    assert status_code == 410
    assert body == {"detail": "Invitation has expired"}
    assert session.invited_employee.status is EmployeeStatus.INVITED
    assert session.commits == 1


def test_revoke_invitation_marks_it_revoked() -> None:
    session = InvitationSession([EmployeeRole.ADMIN])
    app = make_app(session)
    _, issued = request(
        app,
        "POST",
        "/api/v1/invitations",
        body={"email": "new@example.com", "roles": ["AUDITOR"]},
        token="valid-access-token",
    )
    assert issued is not None

    status_code, body = request(
        app,
        "DELETE",
        f"/api/v1/invitations/{issued['invitation_id']}",
        token="valid-access-token",
    )
    assert status_code == 204
    assert body is None
    assert session.invitations[0].status is InvitationStatus.REVOKED
    assert session.commits == 2


def test_reissue_invitation_returns_new_id_without_token() -> None:
    session = InvitationSession([EmployeeRole.ADMIN])
    app = make_app(session)
    _, issued = request(
        app,
        "POST",
        "/api/v1/invitations",
        body={"email": "new@example.com", "roles": ["AUDITOR"]},
        token="valid-access-token",
    )
    assert issued is not None

    status_code, body = request(
        app,
        "POST",
        "/api/v1/invitations/reissue",
        body={"email": "new@example.com"},
        token="valid-access-token",
    )
    assert status_code == 201
    assert body is not None
    assert body["invitation_id"] != issued["invitation_id"]
    assert set(body) == {"invitation_id", "inviter_id", "employee_id"}
    assert session.invitations[0].status is InvitationStatus.REVOKED
    assert session.invitations[1].status is InvitationStatus.PENDING
    assert session.commits == 2
