from identity.application.commands.change_email.command import ChangeEmailCommand
from identity.application.exceptions import (
    EmailAlreadyTakenError,
    EmployeeNotFoundError,
    InvalidCurrentPasswordError,
    InvalidEmailError,
    InvalidEmployeeStateError,
)
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import Password


class ChangeEmailHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        employees: EmployeeRepository,
        password_hasher: PasswordHasher,
    ) -> None:
        self._uow = uow
        self._employees = employees
        self._password_hasher = password_hasher

    async def execute(self, command: ChangeEmailCommand):
        employee_id = EmployeeId(command.employee_id)
        new_email = Email(command.new_email)
        password = Password(command.password)

        async with self._uow:
            employee = await self._employees.get_by_id(employee_id)
            
            if employee is None:
                raise EmployeeNotFoundError("Employee not found")

            if employee.password_hash is None:
                raise InvalidEmployeeStateError(
                    "Active employee must have a password hash"
                )
                
            password_is_valid = self._password_hasher.verify(
                password=password, hashed_password=employee.password_hash
            )

            if not password_is_valid:
                raise InvalidCurrentPasswordError("Password is incorrect")

            if new_email == employee.email:
                raise InvalidEmailError("New email must differ from current email")

            new_email_existing = await self._employees.get_by_email(new_email)

            if new_email_existing is not None:
                raise EmailAlreadyTakenError("Email is already taken")

            employee.change_email(new_email)

            await self._employees.save(employee)
            await self._uow.commit()
