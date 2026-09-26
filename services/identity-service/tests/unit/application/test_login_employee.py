import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from identity.application.commands.login_employee.command import LoginEmployeeCommand
from identity.application.commands.login_employee.handler import LoginEmployeeHandler
from identity.application.exceptions import AuthenticationError
from identity.application.ports.security.access_token_issuer import IssuedAccessToken
from identity.application.ports.security.refresh_token_issuer import IssuedRefreshToken
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.refresh_session import RefreshTokenHash
from tests.unit.application.doubles import (
    AccessTokenIssuerStub,
    EmployeeRepositoryFake,
    FixedClock,
    PasswordHasherStub,
    RefreshSessionRepositoryFake,
    RefreshTokenIssuerStub,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)


@dataclass(frozen=True)
class LoginTestContext:
    handler: LoginEmployeeHandler
    uow: UnitOfWorkFake
    employees: EmployeeRepositoryFake
    refresh_sessions: RefreshSessionRepositoryFake
    password_hasher: PasswordHasherStub
    access_token_issuer: AccessTokenIssuerStub
    refresh_token_issuer: RefreshTokenIssuerStub


def make_context(
    employee: EmployeeAccount | None,
    *,
    password_is_valid: bool = True,
) -> LoginTestContext:
    employees = EmployeeRepositoryFake(
        () if employee is None else (employee,)
    )
    refresh_sessions = RefreshSessionRepositoryFake(
        active_at=NOW,
    )
    uow = UnitOfWorkFake()
    password_hasher = PasswordHasherStub(
        password_is_valid=password_is_valid,
    )
    access_token_issuer = AccessTokenIssuerStub(
        IssuedAccessToken(
            plain_token="access-token",
            expires_at=NOW + timedelta(minutes=15),
        )
    )
    refresh_token_issuer = RefreshTokenIssuerStub(
        IssuedRefreshToken(
            plain_token="issued-refresh-token",
            token_hash=RefreshTokenHash("issued-refresh-token-hash"),
        )
    )
    handler = LoginEmployeeHandler(
        uow=uow,
        employees=employees,
        refresh_sessions=refresh_sessions,
        clock=FixedClock(NOW),
        password_hasher=password_hasher,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
        refresh_token_lifetime=REFRESH_TOKEN_LIFETIME,
    )
    return LoginTestContext(
        handler=handler,
        uow=uow,
        employees=employees,
        refresh_sessions=refresh_sessions,
        password_hasher=password_hasher,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
    )


def execute_login(context: LoginTestContext) -> None:
    asyncio.run(
        context.handler.execute(
            LoginEmployeeCommand(
                email="employee@example.com",
                password="valid-password",
            )
        )
    )


def test_active_employee_with_valid_password_receives_tokens() -> None:
    employee = make_employee("employee@example.com")
    context = make_context(employee)

    result = asyncio.run(
        context.handler.execute(
            LoginEmployeeCommand(
                email="employee@example.com",
                password="valid-password",
            )
        )
    )

    assert result.access_token == "access-token"
    assert result.refresh_token == "issued-refresh-token"
    assert result.refresh_token_expires_at == NOW + REFRESH_TOKEN_LIFETIME
    assert len(context.refresh_sessions.added) == 1
    session = context.refresh_sessions.added[0]
    assert session.employee_id == employee.id
    assert session.refresh_token_hash == RefreshTokenHash("issued-refresh-token-hash")
    assert session.refresh_token_hash.value != result.refresh_token
    assert "issued-refresh-token" not in repr(result)
    assert "issued-refresh-token-hash" not in repr(result)
    assert session.expires_at == NOW + REFRESH_TOKEN_LIFETIME
    assert context.uow.commit_count == 1
    assert context.uow.rollback_count == 0
    assert len(context.password_hasher.verify_calls) == 1
    assert len(context.access_token_issuer.calls) == 1
    assert len(context.refresh_token_issuer.calls) == 1


def test_issued_refresh_token_repr_hides_plain_token_and_hash() -> None:
    issued_token = IssuedRefreshToken(
        plain_token="plain-secret",
        token_hash=RefreshTokenHash("stored-secret-hash"),
    )

    assert "plain-secret" not in repr(issued_token)
    assert "stored-secret-hash" not in repr(issued_token)


def test_missing_employee_returns_generic_authentication_error() -> None:
    context = make_context(None)

    with pytest.raises(AuthenticationError, match="Invalid credentials"):
        execute_login(context)

    assert context.password_hasher.verify_calls == []
    assert context.access_token_issuer.calls == []
    assert context.refresh_token_issuer.calls == []
    assert context.refresh_sessions.added == []
    assert context.uow.commit_count == 0
    assert context.uow.rollback_count == 1


def test_blocked_employee_returns_generic_authentication_error() -> None:
    employee = make_employee(
        "employee@example.com",
        status=EmployeeStatus.BLOCKED,
    )
    context = make_context(employee)

    with pytest.raises(AuthenticationError, match="Invalid credentials"):
        execute_login(context)

    assert context.password_hasher.verify_calls == []
    assert context.access_token_issuer.calls == []
    assert context.refresh_token_issuer.calls == []
    assert context.uow.commit_count == 0
    assert context.uow.rollback_count == 1


def test_invalid_password_returns_generic_authentication_error() -> None:
    employee = make_employee("employee@example.com")
    context = make_context(employee, password_is_valid=False)

    with pytest.raises(AuthenticationError, match="Invalid credentials"):
        execute_login(context)

    assert len(context.password_hasher.verify_calls) == 1
    assert context.access_token_issuer.calls == []
    assert context.refresh_token_issuer.calls == []
    assert context.uow.commit_count == 0
    assert context.uow.rollback_count == 1
