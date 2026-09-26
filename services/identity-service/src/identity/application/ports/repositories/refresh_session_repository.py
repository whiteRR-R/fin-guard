from typing import Protocol

from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import RefreshSessionId


class RefreshSessionRepository(Protocol):
    async def get_by_id(
        self,
        session_id: RefreshSessionId,
    ) -> RefreshSession | None: ...

    async def list_active_by_employee(
        self,
        employee_id: EmployeeId,
    ) -> list[RefreshSession]: ...

    async def add(self, refresh_session: RefreshSession) -> None: ...

    async def save(self, refresh_session: RefreshSession) -> None: ...
