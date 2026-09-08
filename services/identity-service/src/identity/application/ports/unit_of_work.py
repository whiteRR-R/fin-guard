from types import TracebackType
from typing import Protocol

from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.application.ports.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)


class UnitOfWork(Protocol):
    @property
    def employees(self) -> EmployeeRepository: ...

    @property
    def invitations(self) -> InvitationRepository: ...

    @property
    def refresh_sessions(self) -> RefreshSessionRepository: ...

    async def __aenter__(self): ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
