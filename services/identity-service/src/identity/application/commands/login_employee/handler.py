from datetime import timedelta

from identity.application.commands.login_employee.command import LoginEmployeeCommand
from identity.application.commands.login_employee.result import LoginEmployeeResult
from identity.application.exceptions import AuthenticationError
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.application.ports.security.access_token_issuer import AccessTokenIssuer
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.security.refresh_token_issuer import RefreshTokenIssuer
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.password import Password
from identity.domain.value_objects.refresh_session import RefreshSessionId


class LoginEmployeeHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        employees: EmployeeRepository,
        refresh_sessions: RefreshSessionRepository,
        password_hasher: PasswordHasher,
        access_token_issuer: AccessTokenIssuer,
        refresh_token_issuer: RefreshTokenIssuer,
        refresh_token_lifetime: timedelta,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._employees = employees
        self._refresh_sessions = refresh_sessions
        self._password_hasher = password_hasher
        self._access_token_issuer = access_token_issuer
        self._refresh_token_issuer = refresh_token_issuer
        self._refresh_token_lifetime = refresh_token_lifetime

    async def execute(self, command: LoginEmployeeCommand):
        employee_email = Email(command.email)
        employee_password = Password(command.password)
        now = self._clock.now()

        async with self._uow:
            employee = await self._employees.get_by_email(employee_email)

            if employee is None:
                raise AuthenticationError("Invalid credentials")

            if employee.status is not EmployeeStatus.ACTIVE or employee.password_hash is None:
                raise AuthenticationError("Invalid credentials")

            password_is_verified = self._password_hasher.verify(
                employee_password, employee.password_hash
            )

            if not password_is_verified:
                raise AuthenticationError("Invalid credentials")

            session_id = RefreshSessionId.new()

            issued_refresh_token = self._refresh_token_issuer.issue(
                session_id=session_id
            )

            refresh_expires_at = self._refresh_token_lifetime + now

            refresh_session = RefreshSession.start(
                session_id=session_id,
                employee_id=employee.id,
                refresh_token_hash=issued_refresh_token.token_hash,
                created_at=now,
                expires_at=refresh_expires_at,
            )

            issued_access_token = self._access_token_issuer.issue(
                employee_id=employee.id,
                session_id=session_id,
                roles=employee.roles,
                issued_at=now,
            )

            await self._refresh_sessions.add(refresh_session)
            await self._uow.commit()

        return LoginEmployeeResult(
            access_token=issued_access_token.plain_token,
            refresh_token=issued_refresh_token.plain_token,
            refresh_token_expires_at=refresh_expires_at
        )
