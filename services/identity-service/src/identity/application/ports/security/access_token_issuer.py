from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from identity.domain.enums.role import EmployeeRole
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import RefreshSessionId


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    value: str = field(repr=False)
    expires_at: datetime


class AccessTokenIssuer(Protocol):
    def issue(
        self,
        user_id: EmployeeId,
        session_id: RefreshSessionId,
        roles: frozenset[EmployeeRole],
        issued_at: datetime,
    ) -> IssuedAccessToken: ...
