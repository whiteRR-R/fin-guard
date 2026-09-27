import pytest

from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.events.employee import (
    EmployeeActivated,
    EmployeeDeactivated,
    EmployeeInvited,
    EmployeeRoleAssigned,
    EmployeeRoleRevoked,
)
from identity.domain.exceptions import (
    EmployeeIsDeactivatedError,
    EmployeeIsNotInvitedError,
    EmployeeRoleError,
    EmployeeStatusError,
)
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import HashedPassword


def make_invited_employee(
    *,
    roles: tuple[EmployeeRole, ...] = (EmployeeRole.RISK_ANALYST,),
) -> EmployeeAccount:
    return EmployeeAccount.invite(
        employee_id=EmployeeId.new(),
        email=Email("employee@example.com"),
        roles=roles,
    )


def make_active_employee(
    *,
    roles: tuple[EmployeeRole, ...] = (EmployeeRole.RISK_ANALYST,),
) -> EmployeeAccount:
    employee = make_invited_employee(roles=roles)
    employee.pull_events()
    employee.activate(HashedPassword("password-hash"))
    employee.pull_events()
    return employee


def test_invite_creates_invited_account_without_password() -> None:
    employee = make_invited_employee()

    assert employee.status is EmployeeStatus.INVITED
    assert employee.password_hash is None
    assert employee.roles == frozenset({EmployeeRole.RISK_ANALYST})
    events = employee.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], EmployeeInvited)


def test_create_admin_creates_active_account_without_invitation_event() -> None:
    employee_id = EmployeeId.new()
    email = Email("admin@example.com")
    password_hash = HashedPassword("admin-hash")

    employee = EmployeeAccount.create_admin(
        employee_id=employee_id, email=email, password_hash=password_hash
    )

    assert employee.id == employee_id
    assert employee.email == email
    assert employee.roles == frozenset({EmployeeRole.ADMIN})
    assert employee.status is EmployeeStatus.ACTIVE
    assert employee.password_hash == password_hash
    events = employee.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], EmployeeActivated)
    assert events[0].employee_id == employee_id


def test_invite_rejects_empty_roles() -> None:
    with pytest.raises(EmployeeRoleError):
        make_invited_employee(roles=())


def test_invite_removes_duplicate_roles() -> None:
    employee = make_invited_employee(
        roles=(EmployeeRole.AUDITOR, EmployeeRole.AUDITOR),
    )

    assert employee.roles == frozenset({EmployeeRole.AUDITOR})


def test_activate_sets_password_and_records_event() -> None:
    employee = make_invited_employee()
    password_hash = HashedPassword("password-hash")
    employee.pull_events()

    employee.activate(password_hash)

    assert employee.status is EmployeeStatus.ACTIVE
    assert employee.password_hash == password_hash
    events = employee.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], EmployeeActivated)
    assert events[0].employee_id == employee.id


@pytest.mark.parametrize("invalid_hash", [None, "password-hash"])
def test_activate_rejects_invalid_password_hash_without_changing_state(
    invalid_hash: object,
) -> None:
    employee = make_invited_employee()
    employee.pull_events()

    with pytest.raises(TypeError):
        employee.activate(invalid_hash)  # type: ignore[arg-type]

    assert employee.status is EmployeeStatus.INVITED
    assert employee.password_hash is None
    assert employee.pull_events() == ()


def test_activate_can_only_happen_once() -> None:
    employee = make_active_employee()

    with pytest.raises(EmployeeIsNotInvitedError):
        employee.activate(HashedPassword("another-password-hash"))


def test_restore_rejects_active_account_without_password() -> None:
    with pytest.raises(EmployeeStatusError):
        EmployeeAccount.restore(
            employee_id=EmployeeId.new(),
            email=Email("employee@example.com"),
            password_hash=None,
            roles=(EmployeeRole.AUDITOR,),
            status=EmployeeStatus.ACTIVE,
        )


def test_restore_rejects_invited_account_with_password() -> None:
    with pytest.raises(EmployeeStatusError):
        EmployeeAccount.restore(
            employee_id=EmployeeId.new(),
            email=Email("employee@example.com"),
            password_hash=HashedPassword("password-hash"),
            roles=(EmployeeRole.AUDITOR,),
            status=EmployeeStatus.INVITED,
        )


def test_invited_account_cannot_be_blocked() -> None:
    employee = make_invited_employee()
    employee.pull_events()

    with pytest.raises(EmployeeStatusError):
        employee.block()

    assert employee.status is EmployeeStatus.INVITED
    assert employee.pull_events() == ()


def test_assign_role_preserves_existing_roles() -> None:
    employee = make_active_employee()

    employee.assign_role(EmployeeRole.AUDITOR)

    assert employee.roles == frozenset(
        {EmployeeRole.RISK_ANALYST, EmployeeRole.AUDITOR}
    )
    event = employee.pull_events()[0]
    assert isinstance(event, EmployeeRoleAssigned)
    assert event.role is EmployeeRole.AUDITOR


def test_assign_role_does_not_create_duplicates() -> None:
    employee = make_active_employee()

    employee.assign_role(EmployeeRole.AUDITOR)
    employee.assign_role(EmployeeRole.AUDITOR)

    assert employee.roles == frozenset(
        {EmployeeRole.RISK_ANALYST, EmployeeRole.AUDITOR}
    )
    assert len(employee.pull_events()) == 1


def test_revoke_role_removes_only_requested_role() -> None:
    employee = make_active_employee(
        roles=(EmployeeRole.RISK_ANALYST, EmployeeRole.AUDITOR),
    )

    employee.revoke_role(EmployeeRole.AUDITOR)

    assert employee.roles == frozenset({EmployeeRole.RISK_ANALYST})
    assert employee.status is EmployeeStatus.ACTIVE
    event = employee.pull_events()[0]
    assert isinstance(event, EmployeeRoleRevoked)
    assert event.role is EmployeeRole.AUDITOR


def test_revoke_role_cannot_remove_last_role() -> None:
    employee = make_active_employee()

    with pytest.raises(EmployeeRoleError):
        employee.revoke_role(EmployeeRole.RISK_ANALYST)

    assert employee.roles == frozenset({EmployeeRole.RISK_ANALYST})
    assert employee.status is EmployeeStatus.ACTIVE


def test_deactivate_records_event() -> None:
    employee = make_active_employee()

    employee.deactivate()

    assert employee.status is EmployeeStatus.DEACTIVATED
    events = employee.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], EmployeeDeactivated)
    assert events[0].employee_id == employee.id


def test_deactivated_employee_cannot_change_roles() -> None:
    employee = make_active_employee()
    employee.deactivate()
    employee.pull_events()

    with pytest.raises(EmployeeIsDeactivatedError):
        employee.assign_role(EmployeeRole.AUDITOR)

    assert employee.roles == frozenset({EmployeeRole.RISK_ANALYST})
    assert employee.pull_events() == ()
