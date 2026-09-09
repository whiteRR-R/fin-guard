from identity.application.commands.change_email.command import ChangeEmailCommand
from identity.application.exceptions import (
    EmailAlreadyTakenError,
    InvalidCurrentPasswordError,
    InvalidEmailError,
    UserNotFoundError,
)
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import Password


class ChangeEmailHandler:
    def __init__(self, uow: UnitOfWork, password_hasher: PasswordHasher) -> None:
        self._uow = uow
        self._password_hasher = password_hasher

    async def execute(self, command: ChangeEmailCommand):
        user_id = EmployeeId(command.user_id)
        new_email = Email(command.new_email)
        password = Password(command.password)

        async with self._uow:
            user = await self._uow.employees.get_by_id(user_id)

            if user is None:
                raise UserNotFoundError("User not found")

            password_is_valid = self._password_hasher.verify(
                password=password, hashed_password=user.password_hash
            )

            if not password_is_valid:
                raise InvalidCurrentPasswordError("Password is incorrect")

            if new_email == user.email:
                raise InvalidEmailError("New email must differ from current email")

            new_email_existing = await self._uow.employees.get_by_email(new_email)

            if new_email_existing is not None:
                raise EmailAlreadyTakenError("Email is already taken")

            user.change_email(new_email)

            await self._uow.employees.save(user)
            await self._uow.commit()
