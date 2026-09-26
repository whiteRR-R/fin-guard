import asyncio
from datetime import datetime, timezone

import pytest

from identity.application.commands.change_password.command import (
    ChangePasswordCommand,
)
from identity.application.commands.change_password.handler import (
    ChangePasswordHandler,
)
from identity.application.exceptions import EmployeeNotActiveError, InvalidPasswordError
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.password import HashedPassword, Password
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    FixedClock,
    PasswordHasherStub,
    RefreshSessionRepositoryFake,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee, make_refresh_session

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
CURRENT_PASSWORD = "current-password"
NEW_PASSWORD = "different-password"
NEW_PASSWORD_HASH = HashedPassword("new-password-hash")


def test_change_password_revokes_sessions_and_commits_once() -> None:
    employee = make_employee("employee@example.com")
    session = make_refresh_session(employee.id, now=NOW)
    employees = EmployeeRepositoryFake((employee,))
    refresh_sessions = RefreshSessionRepositoryFake(
        active_at=NOW,
        sessions=(session,),
    )
    password_hasher = PasswordHasherStub(
        password_is_valid=True,
        verify_results=(True, False),
        hash_result=NEW_PASSWORD_HASH,
    )
    uow = UnitOfWorkFake()
    handler = ChangePasswordHandler(
        uow=uow,
        employees=employees,
        refresh_sessions=refresh_sessions,
        clock=FixedClock(NOW),
        password_hasher=password_hasher,
    )

    asyncio.run(
        handler.execute(
            ChangePasswordCommand(
                employee_id=employee.id.value,
                current_password=CURRENT_PASSWORD,
                new_password=NEW_PASSWORD,
            )
        )
    )

    assert employee.password_hash == NEW_PASSWORD_HASH
    assert employees.saved == [employee]
    assert refresh_sessions.saved == [session]
    assert not session.is_active(NOW)
    assert password_hasher.hash_calls == [Password(NEW_PASSWORD)]
    assert uow.commit_count == 1
    assert uow.rollback_count == 0


def test_new_password_must_differ_from_current_password() -> None:
    employee = make_employee("employee@example.com")
    employees = EmployeeRepositoryFake((employee,))
    refresh_sessions = RefreshSessionRepositoryFake(active_at=NOW)
    password_hasher = PasswordHasherStub(
        password_is_valid=True,
        verify_results=(True, True),
    )
    uow = UnitOfWorkFake()
    handler = ChangePasswordHandler(
        uow=uow,
        employees=employees,
        refresh_sessions=refresh_sessions,
        clock=FixedClock(NOW),
        password_hasher=password_hasher,
    )

    with pytest.raises(InvalidPasswordError, match="must differ"):
        asyncio.run(
            handler.execute(
                ChangePasswordCommand(
                    employee_id=employee.id.value,
                    current_password=CURRENT_PASSWORD,
                    new_password=NEW_PASSWORD,
                )
            )
        )

    assert password_hasher.hash_calls == []
    assert employees.saved == []
    assert refresh_sessions.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_blocked_employee_cannot_change_password() -> None:
    employee = make_employee(
        "employee@example.com",
        status=EmployeeStatus.BLOCKED,
    )
    employees = EmployeeRepositoryFake((employee,))
    refresh_sessions = RefreshSessionRepositoryFake(active_at=NOW)
    password_hasher = PasswordHasherStub(password_is_valid=True)
    uow = UnitOfWorkFake()
    handler = ChangePasswordHandler(
        uow=uow,
        employees=employees,
        refresh_sessions=refresh_sessions,
        clock=FixedClock(NOW),
        password_hasher=password_hasher,
    )

    with pytest.raises(EmployeeNotActiveError, match="Only active"):
        asyncio.run(
            handler.execute(
                ChangePasswordCommand(
                    employee_id=employee.id.value,
                    current_password=CURRENT_PASSWORD,
                    new_password=NEW_PASSWORD,
                )
            )
        )

    assert password_hasher.verify_calls == []
    assert employees.saved == []
    assert refresh_sessions.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1
