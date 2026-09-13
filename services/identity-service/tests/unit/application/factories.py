from collections.abc import Iterable
from datetime import datetime, timedelta

from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import HashedPassword
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)


def make_employee(
    email: str,
    *,
    roles: Iterable[EmployeeRole] = (EmployeeRole.RISK_ANALYST,),
    status: EmployeeStatus = EmployeeStatus.ACTIVE,
) -> EmployeeAccount:
    password_hash = (
        None
        if status is EmployeeStatus.INVITED
        else HashedPassword("password-hash")
    )
    return EmployeeAccount.restore(
        employee_id=EmployeeId.new(),
        email=Email(email),
        password_hash=password_hash,
        roles=roles,
        status=status,
    )


def make_refresh_session(
    employee_id: EmployeeId,
    *,
    now: datetime,
) -> RefreshSession:
    return RefreshSession.start(
        session_id=RefreshSessionId.new(),
        employee_id=employee_id,
        refresh_token_hash=RefreshTokenHash("refresh-token-hash"),
        created_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
    )
