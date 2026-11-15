import asyncio

import pytest

from identity.application.commands.create_service_account.command import (
    CreateServiceAccountCommand,
)
from identity.application.commands.create_service_account.handler import (
    CreateServiceAccountHandler,
)
from identity.application.commands.revoke_service_account.command import (
    RevokeServiceAccountCommand,
)
from identity.application.commands.revoke_service_account.handler import (
    RevokeServiceAccountHandler,
)
from identity.application.commands.rotate_client_secret.command import (
    RotateClientSecretCommand,
)
from identity.application.commands.rotate_client_secret.handler import (
    RotateClientSecretHandler,
)
from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
    InvalidPaginationError,
    ServiceAccountNotFoundError,
)
from identity.application.messages.client_secret_rotated import (
    ClientSecretRotatedMessage,
)
from identity.application.messages.service_account_created import (
    ServiceAccountCreatedMessage,
)
from identity.application.messages.service_account_revoked import (
    ServiceAccountRevokedMessage,
)
from identity.application.queries.get_service_account.handler import (
    GetServiceAccountHandler,
)
from identity.application.queries.get_service_account.query import (
    GetServiceAccountQuery,
)
from identity.application.queries.list_service_accounts.handler import (
    ListServiceAccountsHandler,
)
from identity.application.queries.list_service_accounts.query import (
    ListServiceAccountsQuery,
)
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.scope import MachineScope
from identity.domain.enums.status import EmployeeStatus, ServiceAccountStatus
from identity.domain.exceptions import (
    ServiceAccountRevokedError,
    ServiceAccountValidationError,
)
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.service_account import ServiceAccountId
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    FixedClock,
    OutboxRepositoryFake,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee
from tests.unit.application.service_account_support import (
    ADMIN_ROLES,
    GRACE,
    NOW,
    ClientCredentialsStub,
    ServiceAccountRepositoryFake,
    hash_of,
    make_service_account,
)

WRITE = MachineScope.TRANSACTIONS_WRITE
READ = MachineScope.TRANSACTIONS_READ


class Context:
    def __init__(self, *, actor_roles=ADMIN_ROLES, actor_status=EmployeeStatus.ACTIVE):
        self.actor = make_employee(
            "admin@example.com", roles=actor_roles, status=actor_status
        )
        self.uow = UnitOfWorkFake()
        self.clock = FixedClock(NOW)
        self.outbox = OutboxRepositoryFake()
        self.employees = EmployeeRepositoryFake((self.actor,))
        self.accounts = ServiceAccountRepositoryFake()
        self.credentials = ClientCredentialsStub()

    def create(self) -> CreateServiceAccountHandler:
        return CreateServiceAccountHandler(
            uow=self.uow,
            clock=self.clock,
            outbox=self.outbox,
            employees=self.employees,
            service_accounts=self.accounts,
            credentials=self.credentials,
        )

    def rotate(self) -> RotateClientSecretHandler:
        return RotateClientSecretHandler(
            uow=self.uow,
            clock=self.clock,
            outbox=self.outbox,
            employees=self.employees,
            service_accounts=self.accounts,
            credentials=self.credentials,
            grace_period=GRACE,
        )

    def revoke(self) -> RevokeServiceAccountHandler:
        return RevokeServiceAccountHandler(
            uow=self.uow,
            clock=self.clock,
            outbox=self.outbox,
            employees=self.employees,
            service_accounts=self.accounts,
        )

    def get(self) -> GetServiceAccountHandler:
        return GetServiceAccountHandler(
            uow=self.uow,
            clock=self.clock,
            employees=self.employees,
            service_accounts=self.accounts,
        )

    def list(self) -> ListServiceAccountsHandler:
        return ListServiceAccountsHandler(
            uow=self.uow,
            clock=self.clock,
            employees=self.employees,
            service_accounts=self.accounts,
        )

    def with_account(self, **kwargs):
        account = make_service_account(**kwargs)
        self.accounts = ServiceAccountRepositoryFake((account,))
        return account

    def assert_nothing_written(self) -> None:
        assert self.accounts.added == []
        assert self.accounts.saved == []
        assert self.outbox.added == []
        assert self.uow.commit_count == 0
        assert self.uow.rollback_count == 1


def run(coroutine):
    return asyncio.run(coroutine)


def test_admin_creates_service_account_and_sees_secret_once() -> None:
    context = Context()

    result = run(
        context.create().execute(
            CreateServiceAccountCommand(
                actor_id=context.actor.id.value,
                name="  Bank X   backend ",
                scopes=(WRITE, READ, WRITE),
            )
        )
    )

    [account] = context.accounts.added
    assert result.service_account_id == account.id.value
    assert result.client_id == account.client_id.value
    assert result.client_secret == "plain-secret-new"
    assert result.scopes == (READ, WRITE)
    assert result.created_at == NOW
    assert account.name.value == "Bank X backend"
    assert account.created_by == context.actor.id
    assert [secret.secret_hash for secret in account.secrets] == [
        hash_of("plain-secret-new")
    ]
    assert "plain-secret-new" not in repr(result)
    assert context.outbox.added == [
        ServiceAccountCreatedMessage(
            message_id=context.outbox.added[0].message_id,
            service_account_id=account.id.value,
            client_id=account.client_id.value,
            actor_id=context.actor.id.value,
            scopes=(READ, WRITE),
            created_at=NOW,
        )
    ]
    assert context.uow.commit_count == 1


@pytest.mark.parametrize(
    ("options", "error"),
    [
        ({"actor_roles": (EmployeeRole.RISK_ANALYST,)}, AccessDeniedError),
        ({"actor_status": EmployeeStatus.BLOCKED}, EmployeeNotActiveError),
    ],
)
def test_only_active_admin_creates_service_account(options, error) -> None:
    context = Context(**options)

    with pytest.raises(error):
        run(
            context.create().execute(
                CreateServiceAccountCommand(
                    actor_id=context.actor.id.value, name="Bank", scopes=(WRITE,)
                )
            )
        )

    context.assert_nothing_written()
    assert context.credentials.issued == []


def test_unknown_actor_cannot_create_service_account() -> None:
    context = Context()

    with pytest.raises(AuthenticationError):
        run(
            context.create().execute(
                CreateServiceAccountCommand(
                    actor_id=EmployeeId.new().value, name="Bank", scopes=(WRITE,)
                )
            )
        )

    context.assert_nothing_written()


def test_service_account_without_scopes_is_rejected() -> None:
    context = Context()

    with pytest.raises(ServiceAccountValidationError, match="scope"):
        run(
            context.create().execute(
                CreateServiceAccountCommand(
                    actor_id=context.actor.id.value, name="Bank", scopes=()
                )
            )
        )

    context.assert_nothing_written()


def test_admin_rotates_secret_and_previous_one_gets_grace_period() -> None:
    context = Context()
    account = context.with_account()

    result = run(
        context.rotate().execute(
            RotateClientSecretCommand(
                actor_id=context.actor.id.value,
                service_account_id=account.id.value,
            )
        )
    )

    assert result.client_secret == "plain-secret-new"
    assert result.previous_secret_expires_at == NOW + GRACE
    assert context.accounts.locked_ids == [account.id]
    assert context.accounts.saved == [account]
    assert {secret.secret_hash for secret in account.active_secrets(NOW)} == {
        hash_of("plain-secret-1"),
        hash_of("plain-secret-new"),
    }
    assert context.outbox.added == [
        ClientSecretRotatedMessage(
            message_id=context.outbox.added[0].message_id,
            service_account_id=account.id.value,
            actor_id=context.actor.id.value,
            previous_secret_expires_at=NOW + GRACE,
            created_at=NOW,
        )
    ]
    assert context.uow.commit_count == 1


def test_rotating_missing_service_account_fails() -> None:
    context = Context()

    with pytest.raises(ServiceAccountNotFoundError):
        run(
            context.rotate().execute(
                RotateClientSecretCommand(
                    actor_id=context.actor.id.value,
                    service_account_id=ServiceAccountId.new().value,
                )
            )
        )

    context.assert_nothing_written()


def test_revoked_service_account_cannot_be_rotated() -> None:
    context = Context()
    account = context.with_account()
    account.revoke(NOW)

    with pytest.raises(ServiceAccountRevokedError):
        run(
            context.rotate().execute(
                RotateClientSecretCommand(
                    actor_id=context.actor.id.value,
                    service_account_id=account.id.value,
                )
            )
        )

    context.assert_nothing_written()


def test_non_admin_cannot_rotate_secret() -> None:
    context = Context(actor_roles=(EmployeeRole.AUDITOR,))
    account = context.with_account()

    with pytest.raises(AccessDeniedError):
        run(
            context.rotate().execute(
                RotateClientSecretCommand(
                    actor_id=context.actor.id.value,
                    service_account_id=account.id.value,
                )
            )
        )

    context.assert_nothing_written()
    assert len(account.active_secrets(NOW)) == 1


def test_admin_revokes_service_account() -> None:
    context = Context()
    account = context.with_account()

    run(
        context.revoke().execute(
            RevokeServiceAccountCommand(
                actor_id=context.actor.id.value,
                service_account_id=account.id.value,
            )
        )
    )

    assert account.status is ServiceAccountStatus.REVOKED
    assert context.accounts.locked_ids == [account.id]
    assert context.accounts.saved == [account]
    assert context.outbox.added == [
        ServiceAccountRevokedMessage(
            message_id=context.outbox.added[0].message_id,
            service_account_id=account.id.value,
            actor_id=context.actor.id.value,
            created_at=NOW,
        )
    ]
    assert context.uow.commit_count == 1


def test_revoking_twice_fails_without_second_audit_message() -> None:
    context = Context()
    account = context.with_account()
    account.revoke(NOW)

    with pytest.raises(ServiceAccountRevokedError):
        run(
            context.revoke().execute(
                RevokeServiceAccountCommand(
                    actor_id=context.actor.id.value,
                    service_account_id=account.id.value,
                )
            )
        )

    context.assert_nothing_written()


def test_non_admin_cannot_revoke_service_account() -> None:
    context = Context(actor_roles=(EmployeeRole.COMPLIANCE_OFFICER,))
    account = context.with_account()

    with pytest.raises(AccessDeniedError):
        run(
            context.revoke().execute(
                RevokeServiceAccountCommand(
                    actor_id=context.actor.id.value,
                    service_account_id=account.id.value,
                )
            )
        )

    assert account.status is ServiceAccountStatus.ACTIVE
    context.assert_nothing_written()


def test_get_service_account_exposes_secret_metadata_but_not_hash() -> None:
    context = Context()
    account = context.with_account()

    view = run(
        context.get().execute(
            GetServiceAccountQuery(
                actor_id=context.actor.id.value,
                service_account_id=account.id.value,
            )
        )
    )

    assert view.service_account_id == account.id.value
    assert view.client_id == account.client_id.value
    assert view.scopes == (READ, WRITE)
    assert view.status is ServiceAccountStatus.ACTIVE
    assert [item.secret_id for item in view.active_secrets] == [
        account.secrets[0].id.value
    ]
    assert "hash:" not in repr(view)


def test_get_missing_service_account_fails() -> None:
    context = Context()

    with pytest.raises(ServiceAccountNotFoundError):
        run(
            context.get().execute(
                GetServiceAccountQuery(
                    actor_id=context.actor.id.value,
                    service_account_id=ServiceAccountId.new().value,
                )
            )
        )


def test_list_service_accounts_is_paginated() -> None:
    context = Context()
    accounts = [make_service_account(client_id="sa_" + letter * 32) for letter in "abc"]
    context.accounts = ServiceAccountRepositoryFake(accounts)

    result = run(
        context.list().execute(
            ListServiceAccountsQuery(actor_id=context.actor.id.value, limit=2)
        )
    )

    assert len(result.service_accounts) == 2
    assert result.has_more is True
    assert context.accounts.requested_pages == [(3, 0)]


@pytest.mark.parametrize(("limit", "offset"), [(0, 0), (101, 0), (10, -1)])
def test_list_rejects_invalid_pagination(limit: int, offset: int) -> None:
    context = Context()

    with pytest.raises(InvalidPaginationError):
        run(
            context.list().execute(
                ListServiceAccountsQuery(
                    actor_id=context.actor.id.value, limit=limit, offset=offset
                )
            )
        )


def test_non_admin_cannot_view_service_accounts() -> None:
    context = Context(actor_roles=(EmployeeRole.RISK_ANALYST,))
    account = context.with_account()

    with pytest.raises(AccessDeniedError):
        run(
            context.get().execute(
                GetServiceAccountQuery(
                    actor_id=context.actor.id.value,
                    service_account_id=account.id.value,
                )
            )
        )
    with pytest.raises(AccessDeniedError):
        run(
            context.list().execute(
                ListServiceAccountsQuery(actor_id=context.actor.id.value)
            )
        )
