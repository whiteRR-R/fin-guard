from identity.application.commands.change_password.command import (
    ChangePasswordCommand,
)
from identity.application.exceptions import (
    EmployeeNotActiveError,
    EmployeeNotFoundError,
    InvalidCurrentPasswordError,
    InvalidEmpolyeeStateError,
    InvalidPasswordError,
)
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import Password


class ChangeUserPasswordHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        employees: EmployeeRepository,
        refresh_sessions: RefreshSessionRepository,
        clock: Clock,
        password_hasher: PasswordHasher,
    ) -> None:
        self._uow = uow
        self._employees = employees
        self._refresh_sessions = refresh_sessions
        self._clock = clock
        self._password_hasher = password_hasher

    async def execute(self, command: ChangePasswordCommand):
        employee_id = EmployeeId(command.employee_id)
        current_password = Password(command.current_password)
        new_password = Password(command.new_password)

        async with self._uow:
            employee = await self._employees.get_by_id(employee_id)

            if employee is None:
                raise EmployeeNotFoundError("User not found")

            if employee.status is not EmployeeStatus.ACTIVE:
                raise EmployeeNotActiveError("Only active employee can change password")

            if employee.password_hash is None:
                raise InvalidEmpolyeeStateError(
                    "Active employee must have a password hash" 
                )
            
            current_password_is_valid = self._password_hasher.verify(
                password=current_password,
                hashed_password=employee.password_hash,
            )

            if not current_password_is_valid:
                raise InvalidCurrentPasswordError("Current password is incorrect")

            new_password_matches_current = self._password_hasher.verify(
                password=new_password, hashed_password=employee.password_hash
            )

            if new_password_matches_current:
                raise InvalidPasswordError(
                    "New password must differ from current password"
                )

            new_password_hash = self._password_hasher.hash(new_password)

            employee.change_password(new_password_hash)

            sessions = await self._refresh_sessions.list_active_by_user(employee_id)

            now = self._clock.now()

            for session in sessions:
                session.revoke(now)
                await self._refresh_sessions.save(session)

            await self._employees.save(employee)
            await self._uow.commit()
