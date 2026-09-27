from identity.application.commands.logout.command import LogoutCommand
from identity.application.exceptions import (
    AccessDeniedError,
    SessionNotFoundError,
)
from identity.application.messages.session_logged_out import SessionLoggedOut
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import RefreshSessionId


class LogoutHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        refresh_session_repository: RefreshSessionRepository,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._refresh_session_repository = refresh_session_repository
        self._outbox_repository = outbox_repository

    async def execute(self, command: LogoutCommand) -> None:
        employee_id = EmployeeId(command.employee_id)
        session_id = RefreshSessionId(command.session_id)

        async with self._uow:
            session = await self._refresh_session_repository.get_by_id_with_lock(
                session_id
            )

            if session is None:
                raise SessionNotFoundError("Session not found")

            if session.employee_id != employee_id:
                raise AccessDeniedError("Session belongs to another employee")

            if session.revoked_at is not None:
                return

            now = self._clock.now()
            outbox_message = SessionLoggedOut(
                session_id=session.id.value,
                employee_id=session.employee_id.value,
                created_at=now,
            )

            session.revoke(now)

            await self._refresh_session_repository.save(session)
            await self._outbox_repository.add(outbox_message)
            await self._uow.commit()
