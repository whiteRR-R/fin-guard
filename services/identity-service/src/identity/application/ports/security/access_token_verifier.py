from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from identity.domain.enums.role import EmployeeRole
from identity.domain.value_objects.refresh_session import RefreshSessionId
from identity.domain.value_objects.employee_id import EmployeeId


@dataclass(frozen=True, kw_only=True, slots=True)
class AccessTokenClaims:
    user_id: EmployeeId
    sid: RefreshSessionId
    roles: frozenset[EmployeeRole]
    expires_at: datetime


class AccessTokenVerifier(Protocol):
    def verify(self, access_token: str) -> AccessTokenClaims: ...
