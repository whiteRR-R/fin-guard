import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from identity.application.authentication.authenticate_access_token import (
    AuthenticateAccessToken,
)
from identity.application.exceptions import AuthenticationError
from identity.application.ports.security.access_token_verifier import (
    AccessTokenClaims,
)
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from tests.unit.application.doubles import (
    AccessTokenVerifierStub,
    EmployeeRepositoryFake,
    FixedClock,
    RefreshSessionRepositoryFake,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee, make_refresh_session

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def make_authenticator(
    *,
    employee_status: EmployeeStatus = EmployeeStatus.ACTIVE,
    token_expires_at: datetime = NOW + timedelta(minutes=5),
    revoke_session: bool = False,
) -> tuple[
    AuthenticateAccessToken,
    UnitOfWorkFake,
    EmployeeRepositoryFake,
    RefreshSessionRepositoryFake,
    AccessTokenVerifierStub,
]:
    employee = make_employee(
        "admin@example.com",
        roles=(EmployeeRole.ADMIN,),
        status=employee_status,
    )
    session = make_refresh_session(employee.id, now=NOW)
    if revoke_session:
        session.revoke(NOW - timedelta(seconds=1))

    claims = AccessTokenClaims(
        employee_id=employee.id,
        sid=session.id,
        roles=frozenset({EmployeeRole.RISK_ANALYST}),
        expires_at=token_expires_at,
    )
    verifier = AccessTokenVerifierStub(claims)
    employees = EmployeeRepositoryFake((employee,))
    refresh_sessions = RefreshSessionRepositoryFake(
        active_at=NOW,
        sessions=(session,),
    )
    uow = UnitOfWorkFake()
    authenticator = AuthenticateAccessToken(
        clock=FixedClock(NOW),
        uow=uow,
        employees=employees,
        refresh_sessions=refresh_sessions,
        access_token_verifier=verifier,
    )
    return authenticator, uow, employees, refresh_sessions, verifier


def test_returns_current_roles_from_employee_account() -> None:
    authenticator, uow, employees, _, verifier = make_authenticator()

    actor = asyncio.run(authenticator.execute("access-token"))

    assert actor.roles == frozenset({EmployeeRole.ADMIN})
    assert actor.employee_id == employees.requested_ids[0]
    assert verifier.received_tokens == ["access-token"]
    assert uow.commit_count == 0


def test_rejects_expired_access_token_before_opening_unit_of_work() -> None:
    authenticator, uow, employees, refresh_sessions, _ = make_authenticator(
        token_expires_at=NOW
    )

    with pytest.raises(AuthenticationError, match="expired"):
        asyncio.run(authenticator.execute("access-token"))

    assert refresh_sessions.requested_ids == []
    assert employees.requested_ids == []
    assert uow.rollback_count == 0


def test_rejects_revoked_session_before_loading_employee() -> None:
    authenticator, uow, employees, refresh_sessions, _ = make_authenticator(
        revoke_session=True
    )

    with pytest.raises(AuthenticationError, match="revoked"):
        asyncio.run(authenticator.execute("access-token"))

    assert len(refresh_sessions.requested_ids) == 1
    assert employees.requested_ids == []
    assert uow.rollback_count == 1


def test_rejects_inactive_employee() -> None:
    authenticator, uow, employees, refresh_sessions, _ = make_authenticator(
        employee_status=EmployeeStatus.BLOCKED,
    )

    with pytest.raises(AuthenticationError, match="not active"):
        asyncio.run(authenticator.execute("access-token"))

    assert len(refresh_sessions.requested_ids) == 1
    assert len(employees.requested_ids) == 1
    assert uow.rollback_count == 1
