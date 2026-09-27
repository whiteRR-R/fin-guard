import asyncio

import pytest

from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
    EmployeeNotFoundError,
)
from identity.application.queries.get_employee.handler import GetEmployeeHandler
from identity.application.queries.get_employee.query import GetEmployeeQuery
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId
from tests.unit.application.doubles import EmployeeRepositoryFake, UnitOfWorkFake
from tests.unit.application.factories import make_employee


@pytest.fixture
def employee() -> EmployeeAccount:
    return make_employee(
        "employee@example.com",
        roles=(EmployeeRole.RISK_ANALYST, EmployeeRole.AUDITOR),
    )


def make_handler(
    *employees: EmployeeAccount,
) -> tuple[GetEmployeeHandler, EmployeeRepositoryFake, UnitOfWorkFake]:
    repository = EmployeeRepositoryFake(employees)
    uow = UnitOfWorkFake()
    handler = GetEmployeeHandler(uow=uow, employee_repository=repository)
    return handler, repository, uow


@pytest.mark.parametrize(
    "roles",
    [
        (EmployeeRole.ADMIN,),
        (EmployeeRole.COMPLIANCE_OFFICER,),
        (EmployeeRole.ADMIN, EmployeeRole.COMPLIANCE_OFFICER),
        (EmployeeRole.AUDITOR, EmployeeRole.COMPLIANCE_OFFICER),
    ],
)
def test_allowed_actor_receives_safe_employee_data(
    employee: EmployeeAccount,
    roles: tuple[EmployeeRole, ...],
) -> None:
    actor = make_employee("actor@example.com", roles=roles)
    handler, repository, uow = make_handler(actor, employee)

    result = asyncio.run(
        handler.execute(
            GetEmployeeQuery(actor_id=actor.id.value, employee_id=employee.id.value)
        )
    )

    assert result.employee_id == employee.id.value
    assert result.email == employee.email.value
    assert result.status is EmployeeStatus.ACTIVE
    assert result.roles == (EmployeeRole.AUDITOR, EmployeeRole.RISK_ANALYST)
    assert not hasattr(result, "password_hash")
    assert employee.password_hash is not None
    assert employee.password_hash.value not in repr(result)
    assert repository.requested_ids == [actor.id, employee.id]
    assert repository.saved == []
    assert repository.added == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 0


@pytest.mark.parametrize(
    "roles",
    [
        (EmployeeRole.RISK_ANALYST,),
        (EmployeeRole.AUDITOR,),
        (EmployeeRole.RISK_ANALYST, EmployeeRole.AUDITOR),
    ],
)
def test_unprivileged_actor_is_rejected_before_employee_lookup(
    employee: EmployeeAccount,
    roles: tuple[EmployeeRole, ...],
) -> None:
    actor = make_employee("actor@example.com", roles=roles)
    handler, repository, uow = make_handler(actor, employee)

    with pytest.raises(AccessDeniedError):
        asyncio.run(
            handler.execute(
                GetEmployeeQuery(actor_id=actor.id.value, employee_id=employee.id.value)
            )
        )

    assert repository.requested_ids == [actor.id]
    assert repository.saved == []
    assert uow.commit_count == 0


@pytest.mark.parametrize(
    "status",
    [EmployeeStatus.INVITED, EmployeeStatus.BLOCKED, EmployeeStatus.DEACTIVATED],
)
def test_inactive_actor_is_rejected_before_employee_lookup(
    employee: EmployeeAccount,
    status: EmployeeStatus,
) -> None:
    actor = make_employee("actor@example.com", roles=(EmployeeRole.ADMIN,), status=status)
    handler, repository, uow = make_handler(actor, employee)

    with pytest.raises(EmployeeNotActiveError):
        asyncio.run(
            handler.execute(
                GetEmployeeQuery(actor_id=actor.id.value, employee_id=employee.id.value)
            )
        )

    assert repository.requested_ids == [actor.id]
    assert uow.commit_count == 0


def test_missing_actor_returns_authentication_error(employee: EmployeeAccount) -> None:
    handler, repository, uow = make_handler(employee)
    missing_actor_id = EmployeeId.new()

    with pytest.raises(AuthenticationError, match="Invalid actor"):
        asyncio.run(
            handler.execute(
                GetEmployeeQuery(
                    actor_id=missing_actor_id.value,
                    employee_id=employee.id.value,
                )
            )
        )

    assert repository.requested_ids == [missing_actor_id]
    assert uow.commit_count == 0


def test_missing_target_returns_employee_not_found() -> None:
    actor = make_employee("actor@example.com", roles=(EmployeeRole.ADMIN,))
    handler, repository, uow = make_handler(actor)
    missing_employee_id = EmployeeId.new()

    with pytest.raises(EmployeeNotFoundError, match="Employee not found"):
        asyncio.run(
            handler.execute(
                GetEmployeeQuery(
                    actor_id=actor.id.value,
                    employee_id=missing_employee_id.value,
                )
            )
        )

    assert repository.requested_ids == [actor.id, missing_employee_id]
    assert uow.commit_count == 0


@pytest.mark.parametrize("status", list(EmployeeStatus))
def test_authorized_actor_can_view_employee_in_any_status(status: EmployeeStatus) -> None:
    actor = make_employee("actor@example.com", roles=(EmployeeRole.ADMIN,))
    employee = make_employee("employee@example.com", status=status)
    handler, repository, uow = make_handler(actor, employee)

    result = asyncio.run(
        handler.execute(
            GetEmployeeQuery(actor_id=actor.id.value, employee_id=employee.id.value)
        )
    )

    assert result.status is status
    assert employee.status is status
    assert repository.saved == []
    assert uow.commit_count == 0
