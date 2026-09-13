import asyncio
from datetime import datetime, timezone

import pytest

from identity.application.commands.block_employee.command import BlockUserCommand
from identity.application.commands.block_employee.handler import BlockEmployeeHandler
from identity.application.exceptions import AccessDeniedError, AuthenticationError
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.policies.employee_block import EmployeeBlockPolicy
from identity.domain.value_objects.employee_id import EmployeeId
from tests.unit.application.doubles import FixedClock, UnitOfWorkFake
from tests.unit.application.factories import make_employee, make_refresh_session

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def test_active_admin_blocks_employee_and_revokes_active_sessions() -> None:
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    employee = make_employee("analyst@example.com")
    session = make_refresh_session(employee.id, now=NOW)
    uow = UnitOfWorkFake(
        active_at=NOW,
        employees=(admin, employee),
        sessions=(session,),
    )
    handler = BlockEmployeeHandler(
        uow=uow,
        clock=FixedClock(NOW),
        block_policy=EmployeeBlockPolicy(),
    )

    result = asyncio.run(
        handler.execute(
            BlockUserCommand(
                actor_id=admin.id.value,
                target_id=employee.id.value,
            )
        )
    )

    assert result.user_id == employee.id.value
    assert result.status == EmployeeStatus.BLOCKED.value
    assert employee.status is EmployeeStatus.BLOCKED
    assert not session.is_active(NOW)
    assert uow.employees.saved == [employee]
    assert uow.refresh_sessions.saved == [session]
    assert uow.commit_count == 1
    assert uow.rollback_count == 0


def test_non_admin_cannot_block_employee() -> None:
    analyst = make_employee("analyst@example.com")
    target = make_employee("target@example.com", roles=(EmployeeRole.AUDITOR,))
    uow = UnitOfWorkFake(active_at=NOW, employees=(analyst, target))
    handler = BlockEmployeeHandler(
        uow=uow,
        clock=FixedClock(NOW),
        block_policy=EmployeeBlockPolicy(),
    )

    with pytest.raises(AccessDeniedError, match="not allowed"):
        asyncio.run(
            handler.execute(
                BlockUserCommand(
                    actor_id=analyst.id.value,
                    target_id=target.id.value,
                )
            )
        )

    assert target.status is EmployeeStatus.ACTIVE
    assert uow.employees.saved == []
    assert uow.refresh_sessions.saved == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_missing_actor_is_rejected_before_target_lookup() -> None:
    target = make_employee("target@example.com")
    missing_actor_id = EmployeeId.new()
    uow = UnitOfWorkFake(active_at=NOW, employees=(target,))
    handler = BlockEmployeeHandler(
        uow=uow,
        clock=FixedClock(NOW),
        block_policy=EmployeeBlockPolicy(),
    )

    with pytest.raises(AuthenticationError, match="Invalid actor"):
        asyncio.run(
            handler.execute(
                BlockUserCommand(
                    actor_id=missing_actor_id.value,
                    target_id=target.id.value,
                )
            )
        )

    assert uow.employees.requested_ids == [missing_actor_id]
    assert uow.commit_count == 0
    assert uow.rollback_count == 1
