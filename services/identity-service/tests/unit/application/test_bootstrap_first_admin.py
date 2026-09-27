import asyncio
from datetime import datetime, timezone

import pytest

from identity.application.commands.bootstrap_first_admin.command import (
    BootstrapFirstAdminCommand,
)
from identity.application.commands.bootstrap_first_admin.handler import (
    BootstrapFirstAdminHandler,
)
from identity.application.commands.bootstrap_first_admin.result import (
    BootstrapFirstAdminResult,
)
from identity.application.exceptions import (
    BootstrapAlreadyCompletedError,
    EmailAlreadyTakenError,
)
from identity.application.messages.first_admin_bootstrapped import (
    FirstAdminBootstrapped,
)
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.exceptions import EmailValidationError, PasswordValidationError
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.password import HashedPassword, Password
from tests.unit.application.doubles import FixedClock, PasswordHasherStub
from tests.unit.application.factories import make_employee
from tests.unit.application.onboarding_support import (
    OnboardingContext,
    OnboardingStore,
    make_context,
)

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
PASSWORD = "first-admin-password"


@pytest.fixture
def store() -> OnboardingStore:
    return OnboardingStore()


def make_handler(
    context: OnboardingContext,
) -> tuple[BootstrapFirstAdminHandler, PasswordHasherStub]:
    hasher = PasswordHasherStub(
        password_is_valid=True, hash_result=HashedPassword("admin-hash")
    )
    handler = BootstrapFirstAdminHandler(
        uow=context.uow,
        clock=FixedClock(NOW),
        employees=context.employees,
        bootstrap=context.bootstrap,
        password_hasher=hasher,
        outbox=context.outbox,
    )
    return handler, hasher


def test_bootstrap_creates_active_admin_and_audit_atomically(
    store: OnboardingStore,
) -> None:
    context = make_context(store)
    handler, hasher = make_handler(context)
    command = BootstrapFirstAdminCommand(email=" ADMIN@example.com ", password=PASSWORD)

    result = asyncio.run(handler.execute(command))

    assert store.state.bootstrap_completed
    assert len(store.state.employees) == 1
    employee = next(iter(store.state.employees.values()))
    assert employee.id.value == result.employee_id
    assert employee.email == Email("admin@example.com")
    assert employee.status is EmployeeStatus.ACTIVE
    assert employee.roles == frozenset({EmployeeRole.ADMIN})
    assert employee.password_hash == HashedPassword("admin-hash")
    assert hasher.hash_calls == [Password(PASSWORD)]
    assert len(store.state.messages) == 1
    message = store.state.messages[0]
    assert isinstance(message, FirstAdminBootstrapped)
    assert message.employee_id == result.employee_id
    assert message.created_at == NOW
    assert message.version == 1
    assert PASSWORD not in repr(command)
    assert PASSWORD not in repr(result)
    assert "admin-hash" not in repr(message)
    assert context.uow.commit_count == 1


@pytest.mark.parametrize("status", list(EmployeeStatus))
def test_existing_admin_in_any_status_prevents_bootstrap(
    store: OnboardingStore, status: EmployeeStatus
) -> None:
    employee = make_employee(
        "existing@example.com", roles=(EmployeeRole.ADMIN,), status=status
    )
    store.state.employees[employee.id] = employee
    context = make_context(store)
    handler, hasher = make_handler(context)

    with pytest.raises(BootstrapAlreadyCompletedError):
        asyncio.run(
            handler.execute(BootstrapFirstAdminCommand("admin@example.com", PASSWORD))
        )

    assert len(store.state.employees) == 1
    assert store.state.messages == []
    assert not store.state.bootstrap_completed
    assert hasher.hash_calls == []
    assert context.uow.commit_count == 0


def test_completed_bootstrap_cannot_repeat_even_without_admin_role(
    store: OnboardingStore,
) -> None:
    first_handler, _ = make_handler(make_context(store))
    asyncio.run(
        first_handler.execute(BootstrapFirstAdminCommand("admin@example.com", PASSWORD))
    )
    employee = next(iter(store.state.employees.values()))
    employee.assign_role(EmployeeRole.AUDITOR)
    employee.revoke_role(EmployeeRole.ADMIN)
    context = make_context(store)
    second_handler, hasher = make_handler(context)

    with pytest.raises(BootstrapAlreadyCompletedError):
        asyncio.run(
            second_handler.execute(
                BootstrapFirstAdminCommand("second@example.com", PASSWORD)
            )
        )

    assert len(store.state.employees) == 1
    assert len(store.state.messages) == 1
    assert hasher.hash_calls == []
    context.employees.has_admin.assert_not_awaited()


def test_bootstrap_rejects_occupied_normalized_email(store: OnboardingStore) -> None:
    employee = make_employee("admin@example.com")
    store.state.employees[employee.id] = employee
    context = make_context(store)
    handler, hasher = make_handler(context)

    with pytest.raises(EmailAlreadyTakenError):
        asyncio.run(
            handler.execute(BootstrapFirstAdminCommand(" ADMIN@example.com ", PASSWORD))
        )

    assert not store.state.bootstrap_completed
    assert hasher.hash_calls == []
    assert store.state.messages == []


@pytest.mark.parametrize(
    ("email", "password", "error"),
    [
        ("invalid", PASSWORD, EmailValidationError),
        ("admin@example.com", "short", PasswordValidationError),
    ],
)
def test_invalid_input_does_not_claim_bootstrap(
    store: OnboardingStore, email: str, password: str, error: type[Exception]
) -> None:
    context = make_context(store)
    handler, _ = make_handler(context)

    with pytest.raises(error):
        asyncio.run(handler.execute(BootstrapFirstAdminCommand(email, password)))

    context.bootstrap.try_claim_first_admin.assert_not_awaited()
    assert not store.state.bootstrap_completed


@pytest.mark.parametrize("failure", ["outbox", "commit"])
def test_failed_bootstrap_rolls_back_everything_and_allows_retry(
    store: OnboardingStore, failure: str
) -> None:
    context = make_context(store)
    context.uow.fail_commit = failure == "commit"
    if failure == "outbox":
        context.outbox.add.side_effect = RuntimeError("Outbox failed")
    handler, _ = make_handler(context)
    command = BootstrapFirstAdminCommand("admin@example.com", PASSWORD)

    with pytest.raises(RuntimeError):
        asyncio.run(handler.execute(command))

    assert not store.state.bootstrap_completed
    assert store.state.employees == {}
    assert store.state.messages == []
    assert context.uow.rollback_count == 1

    retry_handler, _ = make_handler(make_context(store))
    asyncio.run(retry_handler.execute(command))
    assert store.state.bootstrap_completed
    assert len(store.state.employees) == 1
    assert len(store.state.messages) == 1


def test_concurrent_bootstraps_create_only_one_admin(store: OnboardingStore) -> None:
    async def run_concurrently() -> list[BootstrapFirstAdminResult | BaseException]:
        first, _ = make_handler(make_context(store))
        second, _ = make_handler(make_context(store))
        return await asyncio.gather(
            first.execute(BootstrapFirstAdminCommand("first@example.com", PASSWORD)),
            second.execute(BootstrapFirstAdminCommand("second@example.com", PASSWORD)),
            return_exceptions=True,
        )

    results = asyncio.run(run_concurrently())

    assert sum(isinstance(result, BootstrapFirstAdminResult) for result in results) == 1
    errors = [
        result for result in results if isinstance(result, BootstrapAlreadyCompletedError)
    ]
    assert len(errors) == 1
    assert len(store.state.employees) == 1
    assert len(store.state.messages) == 1
