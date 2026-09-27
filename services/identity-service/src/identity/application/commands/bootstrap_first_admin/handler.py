from identity.application.commands.bootstrap_first_admin.command import (
    BootstrapFirstAdminCommand,
)
from identity.application.commands.bootstrap_first_admin.result import (
    BootstrapFirstAdminResult,
)
from identity.application.exceptions import (
    BootstrapAlreadyCompletedError,
    EmailAlreadyTakenError,
)
from identity.application.messages.first_admin_bootstrapped import (
    FirstAdminBootstrapped,
)
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.bootstrap_repository import (
    BootstrapRepository,
)
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import Password


class BootstrapFirstAdminHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        employees: EmployeeRepository,
        bootstrap: BootstrapRepository,
        password_hasher: PasswordHasher,
        outbox: OutboxRepository,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._employees = employees
        self._bootstrap = bootstrap
        self._password_hasher = password_hasher
        self._outbox = outbox

    async def execute(
        self, command: BootstrapFirstAdminCommand
    ) -> BootstrapFirstAdminResult:
        email = Email(command.email)
        password = Password(command.password)

        async with self._uow:
            if not await self._bootstrap.try_claim_first_admin():
                raise BootstrapAlreadyCompletedError("First admin bootstrap is completed")

            if await self._employees.has_admin():
                raise BootstrapAlreadyCompletedError("An administrator already exists")

            if await self._employees.get_by_email(email) is not None:
                raise EmailAlreadyTakenError("Email is already taken")

            password_hash = self._password_hasher.hash(password)
            employee = EmployeeAccount.create_admin(
                employee_id=EmployeeId.new(),
                email=email,
                password_hash=password_hash,
            )

            await self._employees.add(employee)
            await self._outbox.add(
                FirstAdminBootstrapped(
                    employee_id=employee.id.value,
                    created_at=self._clock.now(),
                )
            )
            await self._uow.commit()

        return BootstrapFirstAdminResult(employee_id=employee.id.value)
