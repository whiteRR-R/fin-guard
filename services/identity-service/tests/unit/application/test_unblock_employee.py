import asyncio
from datetime import datetime, timezone

import pytest

from identity.application.commands.unblock_employee.command import (
    UnblockEmployeeCommand,
)
from identity.application.commands.unblock_employee.handler import (
    UnblockEmployeeHandler,
)
from identity.application.exceptions import AccessDeniedError, AuthenticationError
from identity.application.messages.employee_unblocked import EmployeeUnblockedMessage
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.policies.employee_unblock import EmployeeUnblockPolicy
from identity.domain.value_objects.employee_id import EmployeeId
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    FixedClock,
    OutboxRepositoryFake,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def test_active_admin_unblocks_employee() -> None:
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    employee = make_employee(
        "employee@example.com",
        status=EmployeeStatus.BLOCKED,
    )
    employees = EmployeeRepositoryFake((admin, employee))
    uow = UnitOfWorkFake()
    outbox = OutboxRepositoryFake()
    handler = UnblockEmployeeHandler(
        uow=uow,
        clock=FixedClock(NOW),
        outbox=outbox,
        employees=employees,
        unblock_policy=EmployeeUnblockPolicy(),
    )

    result = asyncio.run(
        handler.execute(
            UnblockEmployeeCommand(
                actor_id=admin.id.value,
                target_id=employee.id.value,
            )
        )
    )

    assert result.employee_id == employee.id.value
    assert result.status == EmployeeStatus.ACTIVE.value
    assert employee.status is EmployeeStatus.ACTIVE
    assert employees.saved == [employee]
    assert outbox.added == [
        EmployeeUnblockedMessage(
            message_id=outbox.added[0].message_id,
            employee_id=employee.id.value,
            actor_id=admin.id.value,
            created_at=NOW,
        )
    ]
    assert uow.commit_count == 1
    assert uow.rollback_count == 0


def test_non_admin_cannot_unblock_employee() -> None:
    analyst = make_employee("analyst@example.com")
    employee = make_employee(
        "employee@example.com",
        status=EmployeeStatus.BLOCKED,
    )
    employees = EmployeeRepositoryFake((analyst, employee))
    uow = UnitOfWorkFake()
    outbox = OutboxRepositoryFake()
    handler = UnblockEmployeeHandler(
        uow=uow,
        clock=FixedClock(NOW),
        outbox=outbox,
        employees=employees,
        unblock_policy=EmployeeUnblockPolicy(),
    )

    with pytest.raises(AccessDeniedError, match="not allowed"):
        asyncio.run(
            handler.execute(
                UnblockEmployeeCommand(
                    actor_id=analyst.id.value,
                    target_id=employee.id.value,
                )
            )
        )

    assert employee.status is EmployeeStatus.BLOCKED
    assert employees.saved == []
    assert outbox.added == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_missing_actor_is_rejected_before_target_lookup() -> None:
    employee = make_employee(
        "employee@example.com",
        status=EmployeeStatus.BLOCKED,
    )
    missing_actor_id = EmployeeId.new()
    employees = EmployeeRepositoryFake((employee,))
    uow = UnitOfWorkFake()
    outbox = OutboxRepositoryFake()
    handler = UnblockEmployeeHandler(
        uow=uow,
        clock=FixedClock(NOW),
        outbox=outbox,
        employees=employees,
        unblock_policy=EmployeeUnblockPolicy(),
    )

    with pytest.raises(AuthenticationError, match="Invalid actor"):
        asyncio.run(
            handler.execute(
                UnblockEmployeeCommand(
                    actor_id=missing_actor_id.value,
                    target_id=employee.id.value,
                )
            )
        )

    assert employees.requested_ids == [missing_actor_id]
    assert employees.saved == []
    assert outbox.added == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1
