from datetime import datetime
from typing import Protocol

from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)


class RefreshSessionRepository(Protocol):
    async def get_by_id_with_lock(
        self,
        session_id: RefreshSessionId,
    ) -> RefreshSession | None: ...

    async def list_used_refresh_token_hashes(
        self,
        session_id: RefreshSessionId,
    ) -> tuple[RefreshTokenHash, ...]: ...

    async def add_used_refresh_token_hash(
        self,
        session_id: RefreshSessionId,
        token_hash: RefreshTokenHash,
    ) -> None: ...

    async def get_by_id(
        self,
        session_id: RefreshSessionId,
    ) -> RefreshSession | None: ...

    async def list_active_by_employee(
        self,
        employee_id: EmployeeId,
    ) -> list[RefreshSession]: ...

    async def list_active_by_employee_with_lock(
        self,
        employee_id: EmployeeId,
        *,
        active_at: datetime,
    ) -> list[RefreshSession]: ...

    async def add(self, refresh_session: RefreshSession) -> None: ...

    async def save(self, refresh_session: RefreshSession) -> None: ...
