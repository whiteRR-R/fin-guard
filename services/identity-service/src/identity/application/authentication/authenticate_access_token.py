from dataclasses import dataclass

from identity.application.exceptions import AuthenticationError
from identity.application.ports.clock import Clock
from identity.application.ports.security.access_token_verifier import (
    AccessTokenVerifier,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId


@dataclass(frozen=True, slots=True)
class CurrentActor:
    user_id: EmployeeId
    roles: frozenset[EmployeeRole]


class AuthenticateAccessToken:
    def __init__(
        self,
        clock: Clock,
        uow: UnitOfWork,
        access_token_verifier: AccessTokenVerifier,
    ) -> None:
        self._clock = clock
        self._uow = uow
        self._access_token_verifier = access_token_verifier

    async def execute(self, access_token: str) -> CurrentActor:
        claims = self._access_token_verifier.verify(access_token)
        now = self._clock.now()

        if claims.expires_at <= now:
            raise AuthenticationError("Access token expired")

        async with self._uow:
            session = await self._uow.refresh_sessions.get_by_id(claims.sid)

            if session is None:
                raise AuthenticationError("Invalid session")

            if session.employee_id != claims.user_id:
                raise AuthenticationError("Invalid session")

            if not session.is_active(now):
                raise AuthenticationError("Session is revoked")

            user = await self._uow.employees.get_by_id(claims.user_id)

            if user is None or user.status is not EmployeeStatus.ACTIVE:
                raise AuthenticationError("User is not active")

        return CurrentActor(user_id=user.id, roles=user.roles)
