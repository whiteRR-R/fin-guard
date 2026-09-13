import pytest

from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.exceptions import (
    EmployeeBlockNotAllowedError,
    EmployeeDeletionNotAllowedError,
    EmployeeInviteNotAllowedError,
    EmployeeUnblockNotAllowedError,
)
from identity.domain.policies.employee_block import EmployeeBlockPolicy
from identity.domain.policies.employee_deletion import EmployeeDeletionPolicy
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.domain.policies.employee_unblock import EmployeeUnblockPolicy
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import HashedPassword


def make_employee(
    email_local_part: str,
    *,
    role: EmployeeRole,
    status: EmployeeStatus = EmployeeStatus.ACTIVE,
) -> EmployeeAccount:
    return EmployeeAccount.restore(
        employee_id=EmployeeId.new(),
        email=Email(f"{email_local_part}@example.com"),
        password_hash=HashedPassword("password-hash"),
        roles=(role,),
        status=status,
    )


def test_active_admin_can_invite_employee() -> None:
    admin = make_employee("admin", role=EmployeeRole.ADMIN)

    EmployeeInvitePolicy().ensure_allowed(admin)


def test_non_admin_cannot_invite_employee() -> None:
    analyst = make_employee("analyst", role=EmployeeRole.RISK_ANALYST)

    with pytest.raises(EmployeeInviteNotAllowedError, match="administrator"):
        EmployeeInvitePolicy().ensure_allowed(analyst)


def test_inactive_admin_cannot_invite_employee() -> None:
    blocked_admin = make_employee(
        "admin",
        role=EmployeeRole.ADMIN,
        status=EmployeeStatus.BLOCKED,
    )

    with pytest.raises(EmployeeInviteNotAllowedError, match="active"):
        EmployeeInvitePolicy().ensure_allowed(blocked_admin)


def test_admin_can_delete_regular_employee() -> None:
    admin = make_employee("admin", role=EmployeeRole.ADMIN)
    employee = make_employee("analyst", role=EmployeeRole.RISK_ANALYST)

    EmployeeDeletionPolicy().ensure_allowed(actor=admin, target=employee)


def test_regular_employee_cannot_delete_employee() -> None:
    analyst = make_employee("analyst", role=EmployeeRole.RISK_ANALYST)
    target = make_employee("auditor", role=EmployeeRole.AUDITOR)

    with pytest.raises(EmployeeDeletionNotAllowedError, match="administrators"):
        EmployeeDeletionPolicy().ensure_allowed(actor=analyst, target=target)


def test_admin_cannot_block_another_admin() -> None:
    admin = make_employee("admin", role=EmployeeRole.ADMIN)
    other_admin = make_employee("other-admin", role=EmployeeRole.ADMIN)

    with pytest.raises(EmployeeBlockNotAllowedError, match="another administrator"):
        EmployeeBlockPolicy().ensure_allowed(actor=admin, target=other_admin)


def test_inactive_admin_cannot_unblock_employee() -> None:
    blocked_admin = make_employee(
        "admin",
        role=EmployeeRole.ADMIN,
        status=EmployeeStatus.BLOCKED,
    )
    blocked_employee = make_employee(
        "analyst",
        role=EmployeeRole.RISK_ANALYST,
        status=EmployeeStatus.BLOCKED,
    )

    with pytest.raises(EmployeeUnblockNotAllowedError, match="Inactive"):
        EmployeeUnblockPolicy().ensure_allowed(
            actor=blocked_admin,
            target=blocked_employee,
        )
