import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from types import TracebackType
from unittest.mock import AsyncMock

from identity.application.messages.base import OutboxMessage
from identity.application.ports.repositories.bootstrap_repository import (
    BootstrapRepository,
)
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.application.ports.repositories.outbox_repository import OutboxRepository
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.invitation import Invitation
from identity.domain.enums.role import EmployeeRole
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId


@dataclass
class OnboardingState:
    employees: dict[EmployeeId, EmployeeAccount] = field(default_factory=dict)
    invitations: dict[InvitationId, Invitation] = field(default_factory=dict)
    messages: list[OutboxMessage] = field(default_factory=list)
    bootstrap_completed: bool = False


@dataclass
class OnboardingStore:
    state: OnboardingState = field(default_factory=OnboardingState)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class OnboardingUnitOfWork:
    def __init__(self, store: OnboardingStore) -> None:
        self.store = store
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_commit = False
        self._pending: OnboardingState | None = None
        self._committed = False
        self._entered = False

    @property
    def state(self) -> OnboardingState:
        return self._pending if self._pending is not None else self.store.state

    async def __aenter__(self) -> "OnboardingUnitOfWork":
        self._entered = True
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
            self._entered = False

    async def lock_state(self) -> None:
        assert self._entered and self._pending is None
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
class OnboardingContext:
    uow: OnboardingUnitOfWork
    employees: AsyncMock
    invitations: AsyncMock
    bootstrap: AsyncMock
    outbox: AsyncMock


def make_context(store: OnboardingStore) -> OnboardingContext:
    uow = OnboardingUnitOfWork(store)

    async def try_claim_first_admin() -> bool:
        await uow.lock_state()
        if uow.state.bootstrap_completed:
            return False
        uow.state.bootstrap_completed = True
        return True

    async def has_admin() -> bool:
        return any(
            EmployeeRole.ADMIN in employee.roles
            for employee in uow.state.employees.values()
        )

    async def get_employee(employee_id: EmployeeId) -> EmployeeAccount | None:
        return uow.state.employees.get(employee_id)

    async def get_by_email(email: Email) -> EmployeeAccount | None:
        return next(
            (
                employee
                for employee in uow.state.employees.values()
                if employee.email == email
            ),
            None,
        )

    async def save_employee(employee: EmployeeAccount) -> None:
        assert uow._pending is not None
        uow.state.employees[employee.id] = employee

    async def get_invitation_with_lock(
        invitation_id: InvitationId,
    ) -> Invitation | None:
        await uow.lock_state()
        return uow.state.invitations.get(invitation_id)

    async def save_invitation(invitation: Invitation) -> None:
        assert uow._pending is not None
        uow.state.invitations[invitation.id] = invitation

    async def add_message(message: OutboxMessage) -> None:
        assert uow._pending is not None
        uow.state.messages.append(message)

    employees = AsyncMock(spec=EmployeeRepository)
    employees.has_admin.side_effect = has_admin
    employees.get_by_id.side_effect = get_employee
    employees.get_by_email.side_effect = get_by_email
    employees.get_by_email_with_lock.side_effect = get_by_email
    employees.add.side_effect = save_employee
    employees.save.side_effect = save_employee
    invitations = AsyncMock(spec=InvitationRepository)
    invitations.get_by_id_with_lock.side_effect = get_invitation_with_lock
    invitations.save.side_effect = save_invitation
    bootstrap = AsyncMock(spec=BootstrapRepository)
    bootstrap.try_claim_first_admin.side_effect = try_claim_first_admin
    outbox = AsyncMock(spec=OutboxRepository)
    outbox.add.side_effect = add_message
    return OnboardingContext(uow, employees, invitations, bootstrap, outbox)
