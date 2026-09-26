import asyncio

import pytest

from identity.application.commands.change_email.command import ChangeEmailCommand
from identity.application.commands.change_email.handler import ChangeEmailHandler
from identity.application.exceptions import (
    EmailAlreadyTakenError,
    InvalidCurrentPasswordError,
    InvalidEmployeeStateError,
)
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.email import Email
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    PasswordHasherStub,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee

CURRENT_PASSWORD = "current-password"


def test_active_employee_changes_email() -> None:
    employee = make_employee("employee@example.com")
    employees = EmployeeRepositoryFake((employee,))
    password_hasher = PasswordHasherStub(password_is_valid=True)
    uow = UnitOfWorkFake()
    handler = ChangeEmailHandler(
        uow=uow,
        employees=employees,
        password_hasher=password_hasher,
    )

    asyncio.run(
        handler.execute(
            ChangeEmailCommand(
                employee_id=employee.id.value,
                new_email="  NEW@example.com ",
                password=CURRENT_PASSWORD,
            )
        )
    )

    assert employee.email == Email("new@example.com")
    assert employees.saved == [employee]
    assert uow.commit_count == 1
    assert uow.rollback_count == 0


def test_invalid_current_password_does_not_change_email() -> None:
    employee = make_employee("employee@example.com")
    employees = EmployeeRepositoryFake((employee,))
    uow = UnitOfWorkFake()
    handler = ChangeEmailHandler(
        uow=uow,
        employees=employees,
        password_hasher=PasswordHasherStub(password_is_valid=False),
    )

    with pytest.raises(InvalidCurrentPasswordError, match="incorrect"):
        asyncio.run(
            handler.execute(
                ChangeEmailCommand(
                    employee_id=employee.id.value,
                    new_email="new@example.com",
                    password=CURRENT_PASSWORD,
                )
            )
        )

    assert employee.email == Email("employee@example.com")
    assert employees.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_taken_email_is_rejected() -> None:
    employee = make_employee("employee@example.com")
    other_employee = make_employee("taken@example.com")
    employees = EmployeeRepositoryFake((employee, other_employee))
    uow = UnitOfWorkFake()
    handler = ChangeEmailHandler(
        uow=uow,
        employees=employees,
        password_hasher=PasswordHasherStub(password_is_valid=True),
    )

    with pytest.raises(EmailAlreadyTakenError, match="already taken"):
        asyncio.run(
            handler.execute(
                ChangeEmailCommand(
                    employee_id=employee.id.value,
                    new_email="TAKEN@example.com",
                    password=CURRENT_PASSWORD,
                )
            )
        )

    assert employee.email == Email("employee@example.com")
    assert employees.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_invited_employee_without_password_hash_is_rejected() -> None:
    employee = make_employee(
        "employee@example.com",
        status=EmployeeStatus.INVITED,
    )
    employees = EmployeeRepositoryFake((employee,))
    password_hasher = PasswordHasherStub(password_is_valid=True)
    uow = UnitOfWorkFake()
    handler = ChangeEmailHandler(
        uow=uow,
        employees=employees,
        password_hasher=password_hasher,
    )

    with pytest.raises(InvalidEmployeeStateError, match="password hash"):
        asyncio.run(
            handler.execute(
                ChangeEmailCommand(
                    employee_id=employee.id.value,
                    new_email="new@example.com",
                    password=CURRENT_PASSWORD,
                )
            )
        )

    assert password_hasher.verify_calls == []
    assert employees.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1
