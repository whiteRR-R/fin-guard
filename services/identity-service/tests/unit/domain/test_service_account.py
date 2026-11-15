from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from identity.domain.aggregates.service_account import (
    MAX_ROTATION_GRACE_PERIOD,
    USAGE_RECORD_INTERVAL,
    ClientSecret,
    ServiceAccount,
)
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.scope import MachineScope
from identity.domain.enums.status import ServiceAccountStatus
from identity.domain.events.service_account import (
    ClientSecretRotated,
    ServiceAccountCreated,
    ServiceAccountRevoked,
)
from identity.domain.exceptions import (
    InvalidServiceAccountStateError,
    ScopeNotGrantedError,
    ServiceAccountRevokedError,
    ServiceAccountValidationError,
)
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.service_account import (
    ClientId,
    ClientSecretHash,
    ClientSecretId,
    ServiceAccountId,
    ServiceAccountName,
)

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
GRACE = timedelta(hours=24)
WRITE = MachineScope.TRANSACTIONS_WRITE
READ = MachineScope.TRANSACTIONS_READ


def make_account(
    scopes: tuple[MachineScope, ...] = (WRITE, READ),
) -> ServiceAccount:
    account = ServiceAccount.create(
        service_account_id=ServiceAccountId.new(),
        client_id=ClientId("sa_" + "a" * 32),
        name=ServiceAccountName("Bank X backend"),
        scopes=scopes,
        created_by=EmployeeId.new(),
        secret_id=ClientSecretId.new(),
        secret_hash=ClientSecretHash("hash-1"),
        created_at=NOW,
    )
    account.pull_events()
    return account


def rotate(
    account: ServiceAccount,
    *,
    hash_value: str,
    now: datetime,
    grace: timedelta = GRACE,
) -> ClientSecret | None:
    return account.rotate_secret(
        secret_id=ClientSecretId.new(),
        secret_hash=ClientSecretHash(hash_value),
        now=now,
        grace_period=grace,
    )


def active_hashes(account: ServiceAccount, now: datetime) -> set[str]:
    return {secret.secret_hash.value for secret in account.active_secrets(now)}


@pytest.mark.parametrize(
    "value",
    ["", "sa_short", "client_" + "a" * 32, "sa_" + "a" * 65, "sa_" + "-" * 20, 42],
)
def test_client_id_rejects_invalid_format(value: object) -> None:
    with pytest.raises(ServiceAccountValidationError):
        ClientId(value)  # type: ignore[arg-type]


def test_name_is_normalized_and_bounded() -> None:
    assert ServiceAccountName("  Bank   X  ").value == "Bank X"

    with pytest.raises(ServiceAccountValidationError):
        ServiceAccountName("   ")
    with pytest.raises(ServiceAccountValidationError):
        ServiceAccountName("x" * 101)


def test_secret_hash_is_hidden_from_repr() -> None:
    secret_hash = ClientSecretHash("very-secret-hash")

    assert "very-secret-hash" not in repr(secret_hash)
    assert "very-secret-hash" not in repr(make_account().secrets)


def test_scope_values_are_not_employee_roles() -> None:
    role_values = {role.value for role in EmployeeRole}

    assert role_values.isdisjoint(scope.value for scope in MachineScope)


def test_create_makes_active_account_with_one_current_secret() -> None:
    account_id = ServiceAccountId.new()
    account = ServiceAccount.create(
        service_account_id=account_id,
        client_id=ClientId("sa_" + "b" * 32),
        name=ServiceAccountName("Exchange"),
        scopes=[WRITE, WRITE],
        created_by=EmployeeId.new(),
        secret_id=ClientSecretId.new(),
        secret_hash=ClientSecretHash("hash-1"),
        created_at=NOW,
    )

    assert account.status is ServiceAccountStatus.ACTIVE
    assert account.scopes == frozenset({WRITE})
    assert len(account.secrets) == 1
    assert account.secrets[0].is_current
    assert account.can_authenticate(NOW)
    assert account.last_used_at is None
    events = account.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ServiceAccountCreated)
    assert events[0].service_account_id == account_id
    assert account.pull_events() == ()


def test_create_requires_at_least_one_scope() -> None:
    with pytest.raises(ServiceAccountValidationError, match="at least one scope"):
        make_account(scopes=())


@pytest.mark.parametrize("scopes", [(EmployeeRole.ADMIN,), ("transactions:write",)])
def test_create_rejects_roles_and_raw_strings_as_scopes(scopes: tuple) -> None:
    with pytest.raises(TypeError, match="MachineScope"):
        make_account(scopes=scopes)


def test_create_rejects_naive_datetime() -> None:
    with pytest.raises(ServiceAccountValidationError, match="timezone-aware"):
        ServiceAccount.create(
            service_account_id=ServiceAccountId.new(),
            client_id=ClientId("sa_" + "a" * 32),
            name=ServiceAccountName("Bank"),
            scopes=(WRITE,),
            created_by=EmployeeId.new(),
            secret_id=ClientSecretId.new(),
            secret_hash=ClientSecretHash("hash"),
            created_at=NOW.replace(tzinfo=None),
        )


def test_rotation_keeps_previous_secret_during_grace_period() -> None:
    account = make_account()
    rotated_at = NOW + timedelta(days=1)

    previous = rotate(account, hash_value="hash-2", now=rotated_at)

    assert previous is not None
    assert previous.secret_hash.value == "hash-1"
    assert previous.expires_at == rotated_at + GRACE
    assert active_hashes(account, rotated_at) == {"hash-1", "hash-2"}
    assert active_hashes(account, rotated_at + GRACE) == {"hash-2"}
    current = [secret for secret in account.secrets if secret.is_current]
    assert [secret.secret_hash.value for secret in current] == ["hash-2"]
    assert isinstance(account.pull_events()[0], ClientSecretRotated)


def test_rotation_without_grace_invalidates_previous_secret_immediately() -> None:
    account = make_account()

    previous = rotate(account, hash_value="hash-2", now=NOW, grace=timedelta(0))

    assert previous is None
    assert active_hashes(account, NOW) == {"hash-2"}
    assert len(account.secrets) == 1


def test_at_most_two_secrets_are_ever_usable() -> None:
    account = make_account()
    first_rotation = NOW + timedelta(hours=1)
    second_rotation = NOW + timedelta(hours=2)

    rotate(account, hash_value="hash-2", now=first_rotation)
    rotate(account, hash_value="hash-3", now=second_rotation)

    assert active_hashes(account, second_rotation) == {"hash-2", "hash-3"}
    assert len(account.secrets) == 2


def test_rotation_drops_secrets_that_can_no_longer_authenticate() -> None:
    account = make_account()
    rotate(account, hash_value="hash-2", now=NOW)

    rotate(account, hash_value="hash-3", now=NOW + GRACE + timedelta(hours=1))

    assert {secret.secret_hash.value for secret in account.secrets} == {
        "hash-2",
        "hash-3",
    }


@pytest.mark.parametrize(
    "grace",
    [timedelta(seconds=-1), MAX_ROTATION_GRACE_PERIOD + timedelta(seconds=1)],
)
def test_rotation_grace_period_is_bounded(grace: timedelta) -> None:
    account = make_account()

    with pytest.raises(ServiceAccountValidationError, match="Grace period"):
        rotate(account, hash_value="hash-2", now=NOW, grace=grace)

    assert active_hashes(account, NOW) == {"hash-1"}


def test_rotation_rejects_duplicate_secret_id() -> None:
    account = make_account()

    with pytest.raises(ServiceAccountValidationError, match="already exists"):
        account.rotate_secret(
            secret_id=account.secrets[0].id,
            secret_hash=ClientSecretHash("hash-2"),
            now=NOW,
            grace_period=GRACE,
        )


def test_revoke_invalidates_every_secret_including_grace_period() -> None:
    account = make_account()
    rotate(account, hash_value="hash-2", now=NOW)
    account.pull_events()
    revoked_at = NOW + timedelta(minutes=5)

    account.revoke(revoked_at)

    assert account.status is ServiceAccountStatus.REVOKED
    assert account.revoked_at == revoked_at
    assert not account.can_authenticate(revoked_at)
    assert all(secret.revoked_at == revoked_at for secret in account.secrets)
    assert isinstance(account.pull_events()[0], ServiceAccountRevoked)


@pytest.mark.parametrize(
    "operation",
    [
        lambda account: account.revoke(NOW + timedelta(hours=2)),
        lambda account: rotate(account, hash_value="hash-2", now=NOW),
        lambda account: account.authorize_scopes(None),
        lambda account: account.record_usage(NOW + timedelta(hours=2)),
    ],
)
def test_revoked_account_is_terminal(operation) -> None:
    account = make_account()
    account.revoke(NOW + timedelta(hours=1))

    with pytest.raises(ServiceAccountRevokedError):
        operation(account)


def test_revoke_cannot_happen_before_creation() -> None:
    account = make_account()

    with pytest.raises(InvalidServiceAccountStateError):
        account.revoke(NOW - timedelta(seconds=1))


@pytest.mark.parametrize("requested", [None, ()])
def test_missing_scope_request_grants_everything(requested) -> None:
    account = make_account()

    assert account.authorize_scopes(requested) == frozenset({WRITE, READ})


def test_scope_request_can_narrow_granted_scopes() -> None:
    account = make_account()

    assert account.authorize_scopes([READ]) == frozenset({READ})


def test_scope_request_cannot_widen_granted_scopes() -> None:
    account = make_account(scopes=(READ,))

    with pytest.raises(ScopeNotGrantedError):
        account.authorize_scopes([READ, WRITE])


def test_usage_is_recorded_at_most_once_per_interval() -> None:
    account = make_account()

    assert account.record_usage(NOW) is True
    assert account.record_usage(NOW + USAGE_RECORD_INTERVAL / 2) is False
    assert account.last_used_at == NOW
    assert account.record_usage(NOW + USAGE_RECORD_INTERVAL) is True
    assert account.last_used_at == NOW + USAGE_RECORD_INTERVAL


def _secret(
    *,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> ClientSecret:
    return ClientSecret(
        secret_id=ClientSecretId(uuid4()),
        secret_hash=ClientSecretHash("hash"),
        created_at=NOW,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


def _restore(
    *,
    status: ServiceAccountStatus,
    secrets: tuple[ClientSecret, ...],
    revoked_at: datetime | None = None,
) -> ServiceAccount:
    return ServiceAccount.restore(
        service_account_id=ServiceAccountId.new(),
        client_id=ClientId("sa_" + "a" * 32),
        name=ServiceAccountName("Bank"),
        scopes=(WRITE,),
        status=status,
        secrets=secrets,
        created_by=EmployeeId.new(),
        created_at=NOW,
        revoked_at=revoked_at,
        last_used_at=None,
    )


def test_restore_does_not_record_events() -> None:
    account = _restore(status=ServiceAccountStatus.ACTIVE, secrets=(_secret(),))

    assert account.pull_events() == ()


@pytest.mark.parametrize(
    "secrets",
    [
        (),
        (_secret(), _secret()),
        (_secret(expires_at=NOW + GRACE),),
    ],
)
def test_restore_requires_exactly_one_current_secret_for_active_account(
    secrets: tuple[ClientSecret, ...],
) -> None:
    with pytest.raises(InvalidServiceAccountStateError, match="exactly one"):
        _restore(status=ServiceAccountStatus.ACTIVE, secrets=secrets)


def test_restore_rejects_revoked_account_with_current_secret() -> None:
    with pytest.raises(InvalidServiceAccountStateError, match="current secret"):
        _restore(
            status=ServiceAccountStatus.REVOKED,
            secrets=(_secret(),),
            revoked_at=NOW,
        )


def test_restore_rejects_inconsistent_revoked_at() -> None:
    with pytest.raises(InvalidServiceAccountStateError):
        _restore(
            status=ServiceAccountStatus.ACTIVE,
            secrets=(_secret(),),
            revoked_at=NOW,
        )
    with pytest.raises(InvalidServiceAccountStateError):
        _restore(
            status=ServiceAccountStatus.REVOKED,
            secrets=(_secret(revoked_at=NOW),),
        )
