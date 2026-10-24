import pytest
from sqlalchemy import ARRAY, Enum
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.infrastructure.persistence.models import (
    Base,
    EmployeeModel,
    InvitationModel,
    OutboxMessageModel,
    SessionModel,
    UsedRefreshTokenModel,
)
from identity.infrastructure.persistence.models.enum_types import employee_role_type


def test_models_import_and_configure() -> None:
    configure_mappers()

    employee_table = Base.metadata.tables["employee"]
    invitation_table = Base.metadata.tables["invitation"]
    assert employee_table is EmployeeModel.__table__
    assert invitation_table is InvitationModel.__table__
    assert Base.metadata.tables["session"] is SessionModel.__table__
    assert Base.metadata.tables["used_refresh_token"] is UsedRefreshTokenModel.__table__
    assert Base.metadata.tables["outbox_message"] is OutboxMessageModel.__table__
    assert EmployeeModel.sessions.property.uselist is True
    assert SessionModel.employee.property.uselist is False
    employee_roles_type = employee_table.c.roles.type
    invitation_roles_type = invitation_table.c.roles.type
    invitation_status_type = invitation_table.c.status.type
    assert isinstance(employee_roles_type, ARRAY)
    assert isinstance(invitation_roles_type, ARRAY)
    assert isinstance(invitation_status_type, Enum)
    assert employee_roles_type.item_type is employee_role_type
    assert invitation_roles_type.item_type is employee_role_type
    assert invitation_status_type.enum_class is InvitationStatus


def test_used_refresh_token_history_is_unique_per_session() -> None:
    table = Base.metadata.tables["used_refresh_token"]

    assert list(table.primary_key.columns.keys()) == ["session_id", "token_hash"]
    assert next(iter(table.c.session_id.foreign_keys)).target_fullname == "session.id"
    assert table.c.used_at.server_default is not None
    assert "plain_token" not in table.c


def test_outbox_message_has_json_payload_and_pending_index() -> None:
    table = Base.metadata.tables["outbox_message"]
    index = next(index for index in table.indexes if index.name == "ix_outbox_message_pending_created_at")

    assert table.c.payload.type.__class__ is postgresql.JSONB
    assert list(table.primary_key.columns.keys()) == ["message_id"]
    assert str(index.dialect_options["postgresql"]["where"]) == "published_at IS NULL"


@pytest.mark.parametrize(
    ("status_type", "valid_status"),
    [
        (EmployeeModel.__table__.c.status.type, EmployeeStatus.ACTIVE),
        (InvitationModel.__table__.c.status.type, InvitationStatus.PENDING),
    ],
)
def test_status_columns_reject_unknown_strings(
    status_type: Enum,
    valid_status: EmployeeStatus | InvitationStatus,
) -> None:
    processor = status_type.bind_processor(postgresql.dialect())

    assert processor is not None
    assert processor(valid_status) == valid_status.value
    with pytest.raises(LookupError, match="UNKNOWN"):
        processor("UNKNOWN")


@pytest.mark.parametrize(
    "roles_type",
    [
        EmployeeModel.__table__.c.roles.type,
        InvitationModel.__table__.c.roles.type,
    ],
)
def test_role_arrays_reject_unknown_strings(roles_type: ARRAY) -> None:
    dialect = postgresql.dialect()
    processor = roles_type.dialect_impl(dialect).bind_processor(dialect)

    assert processor is not None
    assert processor([EmployeeRole.ADMIN]) == [EmployeeRole.ADMIN.value]
    with pytest.raises(LookupError, match="UNKNOWN"):
        processor(["UNKNOWN"])
