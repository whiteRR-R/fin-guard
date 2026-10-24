import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from types import TracebackType
from unittest.mock import AsyncMock

from identity.application.messages.base import OutboxMessage
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId


@dataclass
class RoleChangeState:
    employees: dict[EmployeeId, EmployeeAccount] = field(default_factory=dict)
    messages: list[OutboxMessage] = field(default_factory=list)


@dataclass
class RoleChangeStore:
    state: RoleChangeState = field(default_factory=RoleChangeState)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RoleChangeUnitOfWork:
    def __init__(self, store: RoleChangeStore) -> None:
        self.store = store
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_commit = False
        self._pending: RoleChangeState | None = None
        self._committed = False

    @property
    def state(self) -> RoleChangeState:
        return self._pending if self._pending is not None else self.store.state

    async def __aenter__(self) -> "RoleChangeUnitOfWork":  # noqa: PYI034
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None or not self._committed:
                await self.rollback()
        finally:
            if self._pending is not None:
                self.store.lock.release()
            self._pending = None

    async def lock_state(self) -> None:
        assert self._pending is None
        await self.store.lock.acquire()
        self._pending = deepcopy(self.store.state)
        await asyncio.sleep(0)

    async def commit(self) -> None:
        assert self._pending is not None
        if self.fail_commit:
            raise RuntimeError("Commit failed")
        self.store.state = self._pending
        self._committed = True
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


@dataclass
class RoleChangeContext:
    uow: RoleChangeUnitOfWork
    employees: AsyncMock
    outbox: AsyncMock


def make_context(store: RoleChangeStore) -> RoleChangeContext:
    uow = RoleChangeUnitOfWork(store)

    async def get_by_id(employee_id: EmployeeId) -> EmployeeAccount | None:
        return uow.state.employees.get(employee_id)

    async def count_active_admins() -> int:
        return sum(
            employee.status is EmployeeStatus.ACTIVE
            and EmployeeRole.ADMIN in employee.roles
            for employee in uow.state.employees.values()
        )

    async def save(employee: EmployeeAccount) -> None:
        assert uow._pending is not None
        uow.state.employees[employee.id] = employee

    async def add_message(message: OutboxMessage) -> None:
        assert uow._pending is not None
        uow.state.messages.append(message)

    employees = AsyncMock(spec=EmployeeRepository)
    employees.lock_role_changes.side_effect = uow.lock_state
    employees.get_by_id.side_effect = get_by_id
    employees.get_by_id_with_lock.side_effect = get_by_id
    employees.count_active_admins.side_effect = count_active_admins
    employees.save.side_effect = save
    outbox = AsyncMock(spec=OutboxRepository)
    outbox.add.side_effect = add_message
    return RoleChangeContext(uow, employees, outbox)
