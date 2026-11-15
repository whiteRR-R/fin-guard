import asyncio
from datetime import datetime, timezone

import pytest

from identity.application.commands.block_employee.command import BlockEmployeeCommand
from identity.application.commands.block_employee.handler import BlockEmployeeHandler
from identity.application.exceptions import AccessDeniedError, AuthenticationError
from identity.application.messages.employee_blocked import EmployeeBlockedMessage
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.policies.employee_block import EmployeeBlockPolicy
from identity.domain.value_objects.employee_id import EmployeeId
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    FixedClock,
    OutboxRepositoryFake,
    RefreshSessionRepositoryFake,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee, make_refresh_session

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def test_active_admin_blocks_employee_and_revokes_active_sessions() -> None:
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    employee = make_employee("analyst@example.com")
    session = make_refresh_session(employee.id, now=NOW)
    employees = EmployeeRepositoryFake((admin, employee))
    refresh_sessions = RefreshSessionRepositoryFake(
        active_at=NOW,
        sessions=(session,),
    )
    uow = UnitOfWorkFake()
    outbox = OutboxRepositoryFake()
    handler = BlockEmployeeHandler(
        uow=uow,
        employees=employees,
        outbox=outbox,
        refresh_sessions=refresh_sessions,
        clock=FixedClock(NOW),
        block_policy=EmployeeBlockPolicy(),
    )

    result = asyncio.run(
        handler.execute(
            BlockEmployeeCommand(
                actor_id=admin.id.value,
                target_id=employee.id.value,
            )
        )
    )

    assert result.employee_id == employee.id.value
    assert result.status == EmployeeStatus.BLOCKED.value
    assert employee.status is EmployeeStatus.BLOCKED
    assert not session.is_active(NOW)
    assert employees.saved == [employee]
    assert refresh_sessions.saved == [session]
    assert outbox.added == [
        EmployeeBlockedMessage(
            message_id=outbox.added[0].message_id,
            employee_id=employee.id.value,
            actor_id=admin.id.value,
            revoked_session_ids=(session.id.value,),
            created_at=NOW,
        )
    ]
    assert uow.commit_count == 1
    assert uow.rollback_count == 0


def test_non_admin_cannot_block_employee() -> None:
    analyst = make_employee("analyst@example.com")
    target = make_employee("target@example.com", roles=(EmployeeRole.AUDITOR,))
    employees = EmployeeRepositoryFake((analyst, target))
    refresh_sessions = RefreshSessionRepositoryFake(active_at=NOW)
    uow = UnitOfWorkFake()
    outbox = OutboxRepositoryFake()
    handler = BlockEmployeeHandler(
        uow=uow,
        employees=employees,
        outbox=outbox,
        refresh_sessions=refresh_sessions,
        clock=FixedClock(NOW),
        block_policy=EmployeeBlockPolicy(),
    )

    with pytest.raises(AccessDeniedError, match="not allowed"):
        asyncio.run(
            handler.execute(
                BlockEmployeeCommand(
                    actor_id=analyst.id.value,
                    target_id=target.id.value,
                )
            )
        )

    assert target.status is EmployeeStatus.ACTIVE
    assert employees.saved == []
    assert refresh_sessions.saved == []
    assert outbox.added == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_missing_actor_is_rejected_before_target_lookup() -> None:
    target = make_employee("target@example.com")
    missing_actor_id = EmployeeId.new()
    employees = EmployeeRepositoryFake((target,))
    refresh_sessions = RefreshSessionRepositoryFake(active_at=NOW)
    uow = UnitOfWorkFake()
    outbox = OutboxRepositoryFake()
    handler = BlockEmployeeHandler(
        uow=uow,
        employees=employees,
        outbox=outbox,
        refresh_sessions=refresh_sessions,
        clock=FixedClock(NOW),
        block_policy=EmployeeBlockPolicy(),
    )

    with pytest.raises(AuthenticationError, match="Invalid actor"):
        asyncio.run(
            handler.execute(
                BlockEmployeeCommand(
                    actor_id=missing_actor_id.value,
                    target_id=target.id.value,
                )
            )
        )

    assert employees.requested_ids == [missing_actor_id]
    assert outbox.added == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


@pytest.mark.parametrize("session_count", [0, 2])
def test_block_writes_exactly_one_audit_message(session_count: int) -> None:
    admin = make_employee("admin@example.com", roles=(EmployeeRole.ADMIN,))
    employee = make_employee("analyst@example.com")
    sessions = tuple(
        make_refresh_session(employee.id, now=NOW) for _ in range(session_count)
    )
    outbox = OutboxRepositoryFake()
    handler = BlockEmployeeHandler(
        uow=UnitOfWorkFake(),
        employees=EmployeeRepositoryFake((admin, employee)),
        outbox=outbox,
        refresh_sessions=RefreshSessionRepositoryFake(active_at=NOW, sessions=sessions),
        clock=FixedClock(NOW),
        block_policy=EmployeeBlockPolicy(),
    )

    asyncio.run(
        handler.execute(
            BlockEmployeeCommand(actor_id=admin.id.value, target_id=employee.id.value)
        )
    )

    assert len(outbox.added) == 1
    message = outbox.added[0]
    assert isinstance(message, EmployeeBlockedMessage)
    assert set(message.revoked_session_ids) == {s.id.value for s in sessions}
