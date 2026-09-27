from identity.application.commands.logout_all_sessions.command import (
    LogoutAllSessionsCommand,
)
from identity.application.exceptions import EmployeeNotFoundError
from identity.application.messages.all_sessions_logged_out import AllSessionsLoggedOut
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.value_objects.employee_id import EmployeeId


class LogoutAllSessionsHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        employee_repository: EmployeeRepository,
        refresh_session_repository: RefreshSessionRepository,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._employee_repository = employee_repository
        self._refresh_session_repository = refresh_session_repository
        self._outbox_repository = outbox_repository

    async def execute(self, command: LogoutAllSessionsCommand) -> None:
        employee_id = EmployeeId(command.employee_id)

        async with self._uow:
            employee = await self._employee_repository.get_by_id(employee_id)

            if employee is None:
                raise EmployeeNotFoundError("Employee not found")

            now = self._clock.now()
            active_sessions = (
                await self._refresh_session_repository.list_active_by_employee_with_lock(
                    employee_id,
                    active_at=now,
                )
            )

            if not active_sessions:
                return

            for session in active_sessions:
                session.revoke(now)
                await self._refresh_session_repository.save(session)

            outbox_message = AllSessionsLoggedOut(
                employee_id=employee_id.value,
                revoked_sessions_count=len(active_sessions),
                created_at=now,
            )
            await self._outbox_repository.add(outbox_message)
            await self._uow.commit()
