import asyncio

import pytest

from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
    InvalidPaginationError,
)
from identity.application.queries.list_employees.handler import ListEmployeesHandler
from identity.application.queries.list_employees.query import ListEmployeesQuery
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId
from tests.unit.application.doubles import EmployeeRepositoryFake, UnitOfWorkFake
from tests.unit.application.factories import make_employee


@pytest.fixture
def admin() -> EmployeeAccount:
    return make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))


@pytest.fixture
def employees() -> tuple[EmployeeAccount, ...]:
    return tuple(
        make_employee(
            f"employee-{status.value.lower()}@example.com",
            roles=(EmployeeRole.RISK_ANALYST, EmployeeRole.AUDITOR),
            status=status,
        )
        for status in EmployeeStatus
    )


def make_handler(
    *employees: EmployeeAccount,
) -> tuple[ListEmployeesHandler, EmployeeRepositoryFake, UnitOfWorkFake]:
    repository = EmployeeRepositoryFake(employees)
    uow = UnitOfWorkFake()
    handler = ListEmployeesHandler(uow=uow, employee_repository=repository)
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
def test_authorized_actor_receives_safe_profiles_in_all_statuses(
    roles: tuple[EmployeeRole, ...],
    employees: tuple[EmployeeAccount, ...],
) -> None:
    actor = make_employee("actor@example.com", roles=roles)
    handler, repository, uow = make_handler(actor, *employees)

    result = asyncio.run(handler.execute(ListEmployeesQuery(actor_id=actor.id.value)))

    expected = {employee.id.value: employee for employee in (actor, *employees)}
    assert len(result.employees) == len(expected)
    assert {item.employee_id for item in result.employees} == set(expected)
    for item in result.employees:
        employee = expected[item.employee_id]
        assert item.email == employee.email.value
        assert item.status is employee.status
        assert set(item.roles) == employee.roles
        assert not hasattr(item, "password_hash")
    assert "password-hash" not in repr(result)
    assert result.limit == 50
    assert result.offset == 0
    assert result.has_more is False
    assert repository.requested_pages == [(51, 0)]
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
def test_unprivileged_actor_is_rejected_before_listing(
    roles: tuple[EmployeeRole, ...],
) -> None:
    actor = make_employee("actor@example.com", roles=roles)
    handler, repository, uow = make_handler(actor)

    with pytest.raises(AccessDeniedError):
        asyncio.run(handler.execute(ListEmployeesQuery(actor_id=actor.id.value)))

    assert repository.requested_pages == []
    assert uow.commit_count == 0


@pytest.mark.parametrize(
    "status",
    [EmployeeStatus.INVITED, EmployeeStatus.BLOCKED, EmployeeStatus.DEACTIVATED],
)
def test_inactive_admin_is_rejected_before_listing(status: EmployeeStatus) -> None:
    actor = make_employee("actor@example.com", roles=(EmployeeRole.ADMIN,), status=status)
    handler, repository, uow = make_handler(actor)

    with pytest.raises(EmployeeNotActiveError):
        asyncio.run(handler.execute(ListEmployeesQuery(actor_id=actor.id.value)))

    assert repository.requested_pages == []
    assert uow.commit_count == 0


def test_missing_actor_is_rejected_before_listing() -> None:
    handler, repository, uow = make_handler()

    with pytest.raises(AuthenticationError):
        asyncio.run(handler.execute(ListEmployeesQuery(actor_id=EmployeeId.new().value)))

    assert repository.requested_pages == []
    assert uow.commit_count == 0


@pytest.mark.parametrize("limit", [0, -1, 101, True, 1.5, "10", None])
def test_invalid_limit_is_rejected_without_repository_access(
    admin: EmployeeAccount,
    limit: int,
) -> None:
    handler, repository, uow = make_handler(admin)

    with pytest.raises(InvalidPaginationError, match="Limit"):
        asyncio.run(
            handler.execute(ListEmployeesQuery(actor_id=admin.id.value, limit=limit))
        )

    assert repository.requested_ids == []
    assert repository.requested_pages == []
    assert uow.commit_count == 0


@pytest.mark.parametrize("offset", [-1, True, 0.5, "0", None])
def test_invalid_offset_is_rejected_without_repository_access(
    admin: EmployeeAccount,
    offset: int,
) -> None:
    handler, repository, uow = make_handler(admin)

    with pytest.raises(InvalidPaginationError, match="Offset"):
        asyncio.run(
            handler.execute(ListEmployeesQuery(actor_id=admin.id.value, offset=offset))
        )

    assert repository.requested_ids == []
    assert repository.requested_pages == []
    assert uow.commit_count == 0


@pytest.mark.parametrize(
    ("limit", "offset", "expected_count", "has_more"),
    [
        (1, 0, 1, True),
        (2, 2, 2, True),
        (2, 3, 2, False),
        (2, 4, 1, False),
        (2, 5, 0, False),
        (100, 0, 5, False),
    ],
)
def test_pagination_and_has_more(
    admin: EmployeeAccount,
    employees: tuple[EmployeeAccount, ...],
    limit: int,
    offset: int,
    expected_count: int,
    has_more: bool,
) -> None:
    handler, repository, uow = make_handler(admin, *employees)

    result = asyncio.run(
        handler.execute(
            ListEmployeesQuery(actor_id=admin.id.value, limit=limit, offset=offset)
        )
    )

    assert len(result.employees) == expected_count
    assert result.has_more is has_more
    assert result.limit == limit
    assert result.offset == offset
    assert repository.requested_pages == [(limit + 1, offset)]
    assert uow.commit_count == 0


def test_pages_cover_all_employees_without_duplicates(
    admin: EmployeeAccount,
    employees: tuple[EmployeeAccount, ...],
) -> None:
    handler, repository, uow = make_handler(*reversed(employees), admin)

    async def read_pages() -> list[EmployeeId]:
        employee_ids: list[EmployeeId] = []
        for offset in (0, 2, 4):
            result = await handler.execute(
                ListEmployeesQuery(actor_id=admin.id.value, limit=2, offset=offset)
            )
            employee_ids.extend(EmployeeId(item.employee_id) for item in result.employees)
        return employee_ids

    employee_ids = asyncio.run(read_pages())

    expected_ids = {employee.id for employee in (admin, *employees)}
    assert len(employee_ids) == len(expected_ids)
    assert set(employee_ids) == expected_ids
    assert employee_ids == sorted(
        expected_ids, key=lambda employee_id: employee_id.value.int
    )
    assert repository.requested_pages == [(3, 0), (3, 2), (3, 4)]
    assert uow.commit_count == 0
