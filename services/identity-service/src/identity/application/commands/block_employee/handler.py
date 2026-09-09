from identity.application.commands.block_employee.command import BlockUserCommand
from identity.application.commands.block_employee.result import BlockUserResult
from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotFoundError,
)
from identity.application.ports.clock import Clock
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.exceptions import EmployeeBlockNotAllowedError
from identity.domain.policies.employee_block import EmployeeBlockPolicy
from identity.domain.value_objects.employee_id import EmployeeId


class BlockEmployeeHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        block_policy: EmployeeBlockPolicy,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._block_policy = block_policy

    async def execute(self, command: BlockUserCommand) -> BlockUserResult:
        target_id = EmployeeId(command.target_id)
        actor_id = EmployeeId(command.actor_id)

        async with self._uow:
            actor = await self._uow.employees.get_by_id(actor_id)

            if actor is None:
                raise AuthenticationError("Invalid actor")

            target = await self._uow.employees.get_by_id(target_id)

            if target is None:
                raise EmployeeNotFoundError("User not found")

            try:
                self._block_policy.ensure_allowed(actor=actor, target=target)
            except EmployeeBlockNotAllowedError as error:
                raise AccessDeniedError("User blocking is not allowed") from error

            target.block()

            sessions = await self._uow.refresh_sessions.list_active_by_user(target_id)

            now = self._clock.now()

            for session in sessions:
                session.revoke(now)
                await self._uow.refresh_sessions.save(session)

            await self._uow.employees.save(target)
            await self._uow.commit()

        return BlockUserResult(user_id=target.id.value, status=target.status.value)
