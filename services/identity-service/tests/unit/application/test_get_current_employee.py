import asyncio

import pytest

from identity.application.exceptions import EmployeeNotActiveError, EmployeeNotFoundError
from identity.application.queries.get_current_employee.handler import (
    GetCurrentEmployeeHandler,
)
from identity.application.queries.get_current_employee.query import GetCurrentEmployeeQuery
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId
from tests.unit.application.doubles import EmployeeRepositoryFake, UnitOfWorkFake
from tests.unit.application.factories import make_employee


def make_handler(
    *employees: EmployeeAccount,
) -> tuple[GetCurrentEmployeeHandler, EmployeeRepositoryFake, UnitOfWorkFake]:
    repository = EmployeeRepositoryFake(employees)
    uow = UnitOfWorkFake()
    handler = GetCurrentEmployeeHandler(uow=uow, employee_repository=repository)
    return handler, repository, uow


@pytest.mark.parametrize(
    "roles",
    [
        (EmployeeRole.ADMIN,),
        (EmployeeRole.RISK_ANALYST,),
        (EmployeeRole.COMPLIANCE_OFFICER,),
        (EmployeeRole.AUDITOR,),
        (EmployeeRole.RISK_ANALYST, EmployeeRole.AUDITOR),
    ],
)
def test_active_employee_receives_own_safe_profile(
    roles: tuple[EmployeeRole, ...],
) -> None:
    employee = make_employee("employee@example.com", roles=roles)
    another_employee = make_employee("another@example.com")
    handler, repository, uow = make_handler(another_employee, employee)

    result = asyncio.run(
        handler.execute(GetCurrentEmployeeQuery(employee_id=employee.id.value))
    )

    assert result.employee_id == employee.id.value
    assert result.email == employee.email.value
    assert result.status is EmployeeStatus.ACTIVE
    assert set(result.roles) == set(roles)
    assert not hasattr(result, "password_hash")
    assert employee.password_hash is not None
    assert employee.password_hash.value not in repr(result)
    assert repository.requested_ids == [employee.id]
    assert repository.saved == []
    assert repository.added == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 0


def test_missing_employee_returns_employee_not_found() -> None:
    handler, repository, uow = make_handler()
    employee_id = EmployeeId.new()

    with pytest.raises(EmployeeNotFoundError, match="Employee not found"):
        asyncio.run(
            handler.execute(GetCurrentEmployeeQuery(employee_id=employee_id.value))
        )

    assert repository.requested_ids == [employee_id]
    assert uow.commit_count == 0


@pytest.mark.parametrize(
    "status",
    [EmployeeStatus.INVITED, EmployeeStatus.BLOCKED, EmployeeStatus.DEACTIVATED],
)
def test_inactive_employee_cannot_read_own_profile(status: EmployeeStatus) -> None:
    employee = make_employee("employee@example.com", status=status)
    handler, repository, uow = make_handler(employee)

    with pytest.raises(EmployeeNotActiveError, match="Employee must be active"):
        asyncio.run(
            handler.execute(GetCurrentEmployeeQuery(employee_id=employee.id.value))
        )

    assert repository.saved == []
    assert repository.added == []
    assert uow.commit_count == 0
