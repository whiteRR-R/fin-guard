from identity.application.ports.clock import Clock
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.application.queries.list_own_sessions.query import ListOwnSessionsQuery
from identity.application.queries.list_own_sessions.result import (
    ListOwnSessionsResult,
    OwnSessionDTO,
)
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import RefreshSessionId


class ListOwnSessionsHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        refresh_session_repository: RefreshSessionRepository,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._refresh_session_repository = refresh_session_repository

    async def execute(self, query: ListOwnSessionsQuery) -> ListOwnSessionsResult:
        employee_id = EmployeeId(query.employee_id)
        current_session_id = RefreshSessionId(query.current_session_id)

        async with self._uow:
            sessions = await self._refresh_session_repository.list_active_by_employee(
                employee_id
            )
            now = self._clock.now()
            active_sessions = [
                session
                for session in sessions
                if session.employee_id == employee_id and session.is_active(now)
            ]
            active_sessions.sort(
                key=lambda session: (
                    session.id == current_session_id,
                    session.created_at,
                    session.id.value.int,
                ),
                reverse=True,
            )
            result = ListOwnSessionsResult(
                sessions=tuple(
                    OwnSessionDTO(
                        session_id=session.id.value,
                        created_at=session.created_at,
                        expires_at=session.expires_at,
                        is_current=session.id == current_session_id,
                    )
                    for session in active_sessions
                )
            )

        return result
