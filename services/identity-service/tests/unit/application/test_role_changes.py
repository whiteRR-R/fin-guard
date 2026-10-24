import asyncio
from datetime import datetime, timezone

import pytest

from identity.application.commands.assign_role.command import AssignRoleCommand
from identity.application.commands.assign_role.handler import AssignRoleHandler
from identity.application.commands.revoke_role.command import RevokeRoleCommand
from identity.application.commands.revoke_role.handler import RevokeRoleHandler
from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
    EmployeeNotFoundError,
    LastActiveAdminError,
)
from identity.application.messages.employee_role_assigned import EmployeeRoleAssigned
from identity.application.messages.employee_role_revoked import EmployeeRoleRevoked
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.events.employee import (
    EmployeeRoleAssigned as EmployeeRoleAssignedEvent,
)
from identity.domain.events.employee import (
    EmployeeRoleRevoked as EmployeeRoleRevokedEvent,
)
from identity.domain.exceptions import EmployeeIsDeactivatedError, EmployeeRoleError
from identity.domain.value_objects.employee_id import EmployeeId
from tests.unit.application.doubles import FixedClock
from tests.unit.application.factories import make_employee
from tests.unit.application.role_changes_support import (
    RoleChangeContext,
    RoleChangeStore,
    make_context,
)

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


@pytest.fixture
def admin() -> EmployeeAccount:
    return make_employee(
        "admin@example.com", roles=(EmployeeRole.ADMIN, EmployeeRole.AUDITOR)
    )


@pytest.fixture
def employee() -> EmployeeAccount:
    return make_employee("employee@example.com", roles=(EmployeeRole.RISK_ANALYST,))


def make_store(*employees: EmployeeAccount) -> RoleChangeStore:
    store = RoleChangeStore()
    store.state.employees = {employee.id: employee for employee in employees}
    return store


def make_assign_handler(context: RoleChangeContext) -> AssignRoleHandler:
    return AssignRoleHandler(
        uow=context.uow,
        clock=FixedClock(NOW),
        employees=context.employees,
        outbox=context.outbox,
    )


def make_revoke_handler(context: RoleChangeContext) -> RevokeRoleHandler:
    return RevokeRoleHandler(
        uow=context.uow,
        clock=FixedClock(NOW),
        employees=context.employees,
        outbox=context.outbox,
    )


async def execute_change(
    action: str,
    context: RoleChangeContext,
    actor_id: EmployeeId,
    employee_id: EmployeeId,
    role: EmployeeRole,
) -> None:
    if action == "assign":
        await make_assign_handler(context).execute(
            AssignRoleCommand(actor_id.value, employee_id.value, role)
        )
    else:
        await make_revoke_handler(context).execute(
            RevokeRoleCommand(actor_id.value, employee_id.value, role)
        )


@pytest.mark.parametrize(
    "status", [EmployeeStatus.ACTIVE, EmployeeStatus.INVITED, EmployeeStatus.BLOCKED]
)
def test_assign_role_updates_employee_and_records_audit(
    admin: EmployeeAccount, status: EmployeeStatus
) -> None:
    employee = make_employee("employee@example.com", status=status)
    store = make_store(admin, employee)
    context = make_context(store)

    asyncio.run(
        make_assign_handler(context).execute(
            AssignRoleCommand(admin.id.value, employee.id.value, EmployeeRole.AUDITOR)
        )
    )

    saved = store.state.employees[employee.id]
    assert saved.roles == frozenset({EmployeeRole.RISK_ANALYST, EmployeeRole.AUDITOR})
    assert saved.status is status
    events = saved.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], EmployeeRoleAssignedEvent)
    assert events[0].role is EmployeeRole.AUDITOR
    assert len(store.state.messages) == 1
    message = store.state.messages[0]
    assert isinstance(message, EmployeeRoleAssigned)
    assert (message.actor_id, message.employee_id, message.role) == (
        admin.id.value, employee.id.value, EmployeeRole.AUDITOR
    )
    assert message.created_at == NOW
    assert message.version == 1
    context.employees.lock_role_changes.assert_awaited_once()
    context.employees.get_by_id_with_lock.assert_awaited_once_with(employee.id)
    assert context.uow.commit_count == 1


def test_revoke_role_updates_employee_and_records_audit(
    admin: EmployeeAccount, employee: EmployeeAccount
) -> None:
    employee.assign_role(EmployeeRole.AUDITOR)
    employee.pull_events()
    store = make_store(admin, employee)
    context = make_context(store)

    asyncio.run(
        make_revoke_handler(context).execute(
            RevokeRoleCommand(admin.id.value, employee.id.value, EmployeeRole.AUDITOR)
        )
    )

    saved = store.state.employees[employee.id]
    assert saved.roles == frozenset({EmployeeRole.RISK_ANALYST})
    events = saved.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], EmployeeRoleRevokedEvent)
    assert events[0].role is EmployeeRole.AUDITOR
    assert len(store.state.messages) == 1
    message = store.state.messages[0]
    assert isinstance(message, EmployeeRoleRevoked)
    assert (message.actor_id, message.employee_id, message.role) == (
        admin.id.value, employee.id.value, EmployeeRole.AUDITOR
    )
    assert message.created_at == NOW
    assert message.version == 1
    context.employees.count_active_admins.assert_not_awaited()
    assert context.uow.commit_count == 1


@pytest.mark.parametrize("action", ["assign", "revoke"])
def test_missing_actor_is_rejected(
    action: str, employee: EmployeeAccount
) -> None:
    store = make_store(employee)
    context = make_context(store)
    actor_id = EmployeeId.new()
    with pytest.raises(AuthenticationError):
        asyncio.run(
            execute_change(action, context, actor_id, employee.id, EmployeeRole.AUDITOR)
        )

    context.employees.get_by_id_with_lock.assert_not_awaited()
    assert context.uow.commit_count == 0


@pytest.mark.parametrize("action", ["assign", "revoke"])
@pytest.mark.parametrize(
    "role", [EmployeeRole.RISK_ANALYST, EmployeeRole.COMPLIANCE_OFFICER]
)
def test_only_admin_can_change_roles(
    action: str, role: EmployeeRole, employee: EmployeeAccount
) -> None:
    actor = make_employee("actor@example.com", roles=(role,))
    store = make_store(actor, employee)
    context = make_context(store)
    with pytest.raises(AccessDeniedError):
        asyncio.run(
            execute_change(action, context, actor.id, employee.id, EmployeeRole.AUDITOR)
        )

    context.employees.get_by_id_with_lock.assert_not_awaited()
    assert context.uow.commit_count == 0


@pytest.mark.parametrize("action", ["assign", "revoke"])
@pytest.mark.parametrize(
    "status",
    [EmployeeStatus.INVITED, EmployeeStatus.BLOCKED, EmployeeStatus.DEACTIVATED],
)
def test_inactive_admin_cannot_change_roles(
    action: str, status: EmployeeStatus, employee: EmployeeAccount
) -> None:
    actor = make_employee(
        "actor@example.com", roles=(EmployeeRole.ADMIN,), status=status
    )
    store = make_store(actor, employee)
    context = make_context(store)
    with pytest.raises(EmployeeNotActiveError):
        asyncio.run(
            execute_change(action, context, actor.id, employee.id, EmployeeRole.AUDITOR)
        )

    context.employees.get_by_id_with_lock.assert_not_awaited()
    assert context.uow.commit_count == 0


@pytest.mark.parametrize("action", ["assign", "revoke"])
def test_missing_target_is_rejected(action: str, admin: EmployeeAccount) -> None:
    store = make_store(admin)
    context = make_context(store)
    employee_id = EmployeeId.new()
    with pytest.raises(EmployeeNotFoundError):
        asyncio.run(
            execute_change(action, context, admin.id, employee_id, EmployeeRole.AUDITOR)
        )

    assert store.state.messages == []
    assert context.uow.commit_count == 0


@pytest.mark.parametrize("action", ["assign", "revoke"])
def test_duplicate_change_is_noop(
    action: str, admin: EmployeeAccount, employee: EmployeeAccount
) -> None:
    store = make_store(admin, employee)
    context = make_context(store)
    role = EmployeeRole.RISK_ANALYST if action == "assign" else EmployeeRole.AUDITOR
    asyncio.run(execute_change(action, context, admin.id, employee.id, role))

    assert store.state.messages == []
    context.employees.save.assert_not_awaited()
    assert context.uow.commit_count == 0


def test_last_active_admin_cannot_lose_admin_role(
    admin: EmployeeAccount,
) -> None:
    inactive_admin = make_employee(
        "blocked@example.com",
        roles=(EmployeeRole.ADMIN,),
        status=EmployeeStatus.BLOCKED,
    )
    store = make_store(admin, inactive_admin)
    context = make_context(store)

    with pytest.raises(LastActiveAdminError):
        asyncio.run(
            make_revoke_handler(context).execute(
                RevokeRoleCommand(admin.id.value, admin.id.value, EmployeeRole.ADMIN)
            )
        )

    assert EmployeeRole.ADMIN in store.state.employees[admin.id].roles
    context.employees.count_active_admins.assert_awaited_once()
    context.employees.save.assert_not_awaited()
    assert store.state.messages == []
    assert context.uow.commit_count == 0


def test_admin_role_can_be_revoked_if_another_active_admin_remains(
    admin: EmployeeAccount,
) -> None:
    second = make_employee(
        "second@example.com", roles=(EmployeeRole.ADMIN, EmployeeRole.AUDITOR)
    )
    store = make_store(admin, second)
    context = make_context(store)

    asyncio.run(
        make_revoke_handler(context).execute(
            RevokeRoleCommand(admin.id.value, second.id.value, EmployeeRole.ADMIN)
        )
    )

    assert store.state.employees[second.id].roles == frozenset({EmployeeRole.AUDITOR})
    assert store.state.employees[admin.id].roles == admin.roles
    assert context.uow.commit_count == 1


def test_revoking_blocked_admin_role_does_not_reduce_active_admin_count(
    admin: EmployeeAccount,
) -> None:
    blocked = make_employee(
        "blocked@example.com",
        roles=(EmployeeRole.ADMIN, EmployeeRole.AUDITOR),
        status=EmployeeStatus.BLOCKED,
    )
    store = make_store(admin, blocked)
    context = make_context(store)

    asyncio.run(
        make_revoke_handler(context).execute(
            RevokeRoleCommand(admin.id.value, blocked.id.value, EmployeeRole.ADMIN)
        )
    )

    assert store.state.employees[blocked.id].roles == frozenset({EmployeeRole.AUDITOR})
    context.employees.count_active_admins.assert_not_awaited()
    assert context.uow.commit_count == 1


def test_revoking_nonadmin_role_keeps_domain_last_role_rule(
    admin: EmployeeAccount, employee: EmployeeAccount
) -> None:
    store = make_store(admin, employee)
    context = make_context(store)

    with pytest.raises(EmployeeRoleError):
        asyncio.run(
            make_revoke_handler(context).execute(
                RevokeRoleCommand(
                    admin.id.value, employee.id.value, EmployeeRole.RISK_ANALYST
                )
            )
        )

    assert store.state.employees[employee.id].roles == frozenset(
        {EmployeeRole.RISK_ANALYST}
    )
    assert store.state.messages == []


@pytest.mark.parametrize("action", ["assign", "revoke"])
def test_deactivated_target_rejected_by_domain(
    action: str, admin: EmployeeAccount
) -> None:
    employee = make_employee("employee@example.com", status=EmployeeStatus.DEACTIVATED)
    store = make_store(admin, employee)
    context = make_context(store)
    role = EmployeeRole.AUDITOR if action == "assign" else EmployeeRole.RISK_ANALYST

    with pytest.raises(EmployeeIsDeactivatedError):
        asyncio.run(execute_change(action, context, admin.id, employee.id, role))

    assert store.state.messages == []
    assert context.uow.commit_count == 0


@pytest.mark.parametrize("action", ["assign", "revoke"])
@pytest.mark.parametrize("failure", ["outbox", "commit"])
def test_failure_rolls_back_role_and_audit(
    action: str, failure: str, admin: EmployeeAccount, employee: EmployeeAccount
) -> None:
    employee.assign_role(EmployeeRole.AUDITOR)
    employee.pull_events()
    store = make_store(admin, employee)
    context = make_context(store)
    context.uow.fail_commit = failure == "commit"
    if failure == "outbox":
        context.outbox.add.side_effect = RuntimeError("Outbox failed")
    role = (
        EmployeeRole.COMPLIANCE_OFFICER
        if action == "assign"
        else EmployeeRole.AUDITOR
    )

    with pytest.raises(RuntimeError):
        asyncio.run(execute_change(action, context, admin.id, employee.id, role))

    assert store.state.employees[employee.id].roles == employee.roles
    assert store.state.messages == []
    assert context.uow.rollback_count == 1


def test_parallel_admin_revocations_leave_one_active_admin() -> None:
    first = make_employee(
        "first@example.com", roles=(EmployeeRole.ADMIN, EmployeeRole.AUDITOR)
    )
    second = make_employee(
        "second@example.com", roles=(EmployeeRole.ADMIN, EmployeeRole.AUDITOR)
    )
    store = make_store(first, second)

    async def run_concurrently() -> list[None | BaseException]:
        first_handler = make_revoke_handler(make_context(store))
        second_handler = make_revoke_handler(make_context(store))
        results = await asyncio.gather(
            first_handler.execute(
                RevokeRoleCommand(first.id.value, first.id.value, EmployeeRole.ADMIN)
            ),
            second_handler.execute(
                RevokeRoleCommand(second.id.value, second.id.value, EmployeeRole.ADMIN)
            ),
            return_exceptions=True,
        )
        return list(results)

    results = asyncio.run(run_concurrently())

    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, LastActiveAdminError) for result in results) == 1
    active_admins = sum(
        EmployeeRole.ADMIN in employee.roles
        for employee in store.state.employees.values()
    )
    assert active_admins == 1
    assert len(store.state.messages) == 1
