from identity.application.commands.block_employee.command import BlockEmployeeCommand
from identity.application.commands.block_employee.result import BlockEmployeeResult
from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotFoundError,
)
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.exceptions import EmployeeBlockNotAllowedError
from identity.domain.policies.employee_block import EmployeeBlockPolicy
from identity.domain.value_objects.employee_id import EmployeeId


class BlockEmployeeHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        employees: EmployeeRepository,
        refresh_sessions: RefreshSessionRepository,
        clock: Clock,
        block_policy: EmployeeBlockPolicy,
    ) -> None:
        self._uow = uow
        self._employees = employees
        self._refresh_sessions = refresh_sessions
        self._clock = clock
        self._block_policy = block_policy

    async def execute(self, command: BlockEmployeeCommand) -> BlockEmployeeResult:
        target_id = EmployeeId(command.target_id)
        actor_id = EmployeeId(command.actor_id)

        async with self._uow:
            actor = await self._employees.get_by_id(actor_id)

            if actor is None:
                raise AuthenticationError("Invalid actor")

            target = await self._employees.get_by_id(target_id)

            if target is None:
                raise EmployeeNotFoundError("Employee not found")

            try:
                self._block_policy.ensure_allowed(actor=actor, target=target)
            except EmployeeBlockNotAllowedError as error:
                raise AccessDeniedError("Employee blocking is not allowed") from error

            target.block()

            sessions = await self._refresh_sessions.list_active_by_employee(target_id)

            now = self._clock.now()

            for session in sessions:
                session.revoke(now)
                await self._refresh_sessions.save(session)

            await self._employees.save(target)
            await self._uow.commit()

        return BlockEmployeeResult(
            employee_id=target.id.value,
            status=target.status.value,
        )
