import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers

from identity.domain.enums.scope import MachineScope
from identity.domain.enums.status import ServiceAccountStatus
from identity.domain.value_objects.service_account import (
    ClientId,
    ClientSecretHash,
    ClientSecretId,
    ServiceAccountId,
)
from identity.infrastructure.persistence.data_mapper.service_account_mapper import (
    ServiceAccountMapper,
)
from identity.infrastructure.persistence.models import (
    Base,
    ServiceAccountModel,
    ServiceAccountSecretModel,
)
from identity.infrastructure.persistence.models.enum_types import (
    machine_scope_type,
)
from identity.infrastructure.persistence.repositories.service_account_repository import (
    ServiceAccountRepository,
)
from tests.unit.application.service_account_support import make_service_account

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _session() -> Mock:
    session = Mock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.execute = AsyncMock()
    return session


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect())).lower()


def _rotate(account, hash_value: str, now: datetime = NOW) -> None:
    account.rotate_secret(
        secret_id=ClientSecretId.new(),
        secret_hash=ClientSecretHash(hash_value),
        now=now,
        grace_period=timedelta(hours=24),
    )


# ---------- models ----------


def test_service_account_tables_are_registered() -> None:
    configure_mappers()

    assert Base.metadata.tables["service_account"] is ServiceAccountModel.__table__
    assert (
        Base.metadata.tables["service_account_secret"]
        is ServiceAccountSecretModel.__table__
    )
    assert ServiceAccountModel.secrets.property.uselist is True
    assert ServiceAccountModel.secrets.property.cascade.delete_orphan is True


def test_service_account_table_enforces_invariants() -> None:
    table = Base.metadata.tables["service_account"]
    constraints = {constraint.name for constraint in table.constraints}

    assert "ck_service_account_scopes_nonempty" in constraints
    assert "ck_service_account_revoked_at_matches_status" in constraints
    assert table.c.client_id.unique is True
    assert table.c.scopes.type.item_type is machine_scope_type
    assert "secret" not in table.c
    assert next(iter(table.c.created_by.foreign_keys)).target_fullname == "employee.id"


def test_only_one_current_secret_per_account_is_allowed() -> None:
    table = Base.metadata.tables["service_account_secret"]
    index = next(
        index
        for index in table.indexes
        if index.name == "uq_service_account_secret_current"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == ["service_account_id"]
    assert (
        str(index.dialect_options["postgresql"]["where"])
        == "expires_at IS NULL AND revoked_at IS NULL"
    )
    foreign_key = next(iter(table.c.service_account_id.foreign_keys))
    assert foreign_key.target_fullname == "service_account.id"
    assert foreign_key.ondelete == "CASCADE"
    assert table.c.secret_hash.unique is True
    assert "plain_secret" not in table.c


def test_machine_scopes_are_stored_by_value() -> None:
    processor = machine_scope_type.bind_processor(postgresql.dialect())

    assert processor is not None
    assert processor(MachineScope.TRANSACTIONS_WRITE) == "transactions:write"
    assert machine_scope_type.enums == [scope.value for scope in MachineScope]


# ---------- mapper ----------


def test_mapper_round_trip_keeps_secrets_and_state() -> None:
    account = make_service_account()
    _rotate(account, "hash-2")
    account.record_usage(NOW)

    model = ServiceAccountMapper.to_model(account)
    restored = ServiceAccountMapper.to_domain(model)

    assert model.scopes == [
        MachineScope.TRANSACTIONS_READ,
        MachineScope.TRANSACTIONS_WRITE,
    ]
    assert len(model.secrets) == 2
    assert all(
        secret.service_account_id == account.id.value for secret in model.secrets
    )
    assert restored.id == account.id
    assert restored.client_id == account.client_id
    assert restored.scopes == account.scopes
    assert restored.last_used_at == NOW
    assert [
        (secret.id, secret.secret_hash, secret.expires_at, secret.revoked_at)
        for secret in restored.secrets
    ] == [
        (secret.id, secret.secret_hash, secret.expires_at, secret.revoked_at)
        for secret in account.secrets
    ]


def test_update_model_syncs_added_changed_and_dropped_secrets() -> None:
    account = make_service_account()
    model = ServiceAccountMapper.to_model(account)
    first_secret_model = model.secrets[0]

    _rotate(account, "hash-2")
    ServiceAccountMapper.update_model(account, model)

    assert model.secrets[0] is first_secret_model
    assert first_secret_model.expires_at == NOW + timedelta(hours=24)
    assert [secret.secret_hash for secret in model.secrets] == [
        "hash:plain-secret-1",
        "hash-2",
    ]

    _rotate(account, "hash-3", now=NOW + timedelta(days=2))
    ServiceAccountMapper.update_model(account, model)

    assert first_secret_model not in model.secrets
    assert [secret.secret_hash for secret in model.secrets] == ["hash-2", "hash-3"]


def test_update_model_persists_revocation() -> None:
    account = make_service_account()
    model = ServiceAccountMapper.to_model(account)

    account.revoke(NOW)
    ServiceAccountMapper.update_model(account, model)

    assert model.status is ServiceAccountStatus.REVOKED
    assert model.revoked_at == NOW
    assert all(secret.revoked_at == NOW for secret in model.secrets)


def test_update_model_rejects_other_account() -> None:
    model = ServiceAccountMapper.to_model(make_service_account())

    with pytest.raises(ValueError, match="does not match"):
        ServiceAccountMapper.update_model(make_service_account(), model)


# ---------- repository ----------


def test_repository_add_and_lookup_queries() -> None:
    session = _session()
    repository = ServiceAccountRepository(session)
    account = make_service_account()

    asyncio.run(repository.add(account))
    added = session.add.call_args.args[0]
    assert isinstance(added, ServiceAccountModel)
    assert added.id == account.id.value

    session.scalar.return_value = ServiceAccountMapper.to_model(account)
    found = asyncio.run(repository.get_by_client_id(account.client_id))
    assert found is not None and found.id == account.id
    assert "service_account.client_id" in _sql(session.scalar.call_args.args[0])

    session.scalar.return_value = None
    assert asyncio.run(repository.get_by_id(ServiceAccountId.new())) is None
    asyncio.run(repository.get_by_id_with_lock(ServiceAccountId.new()))
    assert "for update" in _sql(session.scalar.call_args.args[0])


def test_repository_lists_in_stable_order() -> None:
    session = _session()
    session.scalars.return_value = [
        ServiceAccountMapper.to_model(make_service_account())
    ]
    repository = ServiceAccountRepository(session)

    accounts = asyncio.run(repository.list_page(limit=11, offset=20))

    assert len(accounts) == 1
    sql = _sql(session.scalars.call_args.args[0])
    assert "order by service_account.created_at, service_account.id" in sql
    assert "limit" in sql and "offset" in sql


def test_repository_save_locks_and_updates_existing_row() -> None:
    session = _session()
    account = make_service_account()
    model = ServiceAccountMapper.to_model(account)
    session.scalar.return_value = model
    repository = ServiceAccountRepository(session)

    account.revoke(NOW)
    asyncio.run(repository.save(account))

    assert model.status is ServiceAccountStatus.REVOKED
    assert "for update" in _sql(session.scalar.call_args.args[0])


def test_repository_save_of_missing_account_fails() -> None:
    session = _session()
    session.scalar.return_value = None

    with pytest.raises(LookupError):
        asyncio.run(ServiceAccountRepository(session).save(make_service_account()))


def test_save_last_used_at_updates_only_that_column_and_never_moves_back() -> None:
    session = _session()
    account = make_service_account()
    account.record_usage(NOW)

    asyncio.run(ServiceAccountRepository(session).save_last_used_at(account))

    statement = session.execute.call_args.args[0]
    sql = _sql(statement)
    assert sql.startswith("update service_account set last_used_at=")
    assert "status" not in sql.split("where")[0]
    assert "service_account.last_used_at is null" in sql
    assert "service_account.last_used_at <" in sql


def test_save_last_used_at_without_usage_writes_nothing() -> None:
    session = _session()

    asyncio.run(
        ServiceAccountRepository(session).save_last_used_at(make_service_account())
    )

    session.execute.assert_not_called()


def test_client_id_column_fits_generated_ids() -> None:
    table = Base.metadata.tables["service_account"]

    assert table.c.client_id.type.length >= len(ClientId("sa_" + "a" * 64).value)
