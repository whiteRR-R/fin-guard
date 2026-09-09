from identity.application.commands.change_password.command import (
    ChangePasswordCommand,
)
from identity.application.exceptions import (
    InvalidCurrentPasswordError,
    InvalidPasswordError,
    UserNotFoundError,
)
from identity.application.ports.clock import Clock
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import Password


class ChangeUserPasswordHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        password_hasher: PasswordHasher,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._password_hasher = password_hasher

    async def execute(self, command: ChangePasswordCommand):
        user_id = EmployeeId(command.user_id)
        current_password = Password(command.current_password)
        new_password = Password(command.new_password)

        async with self._uow:
            user = await self._uow.employees.get_by_id(user_id)

            if user is None:
                raise UserNotFoundError("User not found")

            current_password_is_valid = self._password_hasher.verify(
                password=current_password,
                hashed_password=user.password_hash,
            )

            if not current_password_is_valid:
                raise InvalidCurrentPasswordError("Current password is incorrect")

            new_password_matches_current = self._password_hasher.verify(
                password=new_password, hashed_password=user.password_hash
            )

            if new_password_matches_current:
                raise InvalidPasswordError(
                    "New password must differ from current password"
                )

            new_password_hash = self._password_hasher.hash(new_password)
            
            user.change_password(new_password_hash)
            
            sessions = await self._uow.refresh_sessions.list_active_by_user(user_id)

            now = self._clock.now()

            for session in sessions:
                session.revoke(now)
                await self._uow.refresh_sessions.save(session)

            await self._uow.employees.save(user)
            await self._uow.commit()
