from sqlalchemy.orm import configure_mappers

from identity.domain.enums.status import InvitationStatus
from identity.infrastructure.persistence.models import (
    Base,
    EmployeeModel,
    InvitationModel,
    SessionModel,
)
from identity.infrastructure.persistence.models.enum_types import employee_role_type


def test_models_import_and_configure() -> None:
    configure_mappers()

    assert Base.metadata.tables["employee"] is EmployeeModel.__table__
    assert Base.metadata.tables["invitation"] is InvitationModel.__table__
    assert Base.metadata.tables["session"] is SessionModel.__table__
    assert EmployeeModel.sessions.property.uselist is True
    assert SessionModel.employee.property.uselist is False
    assert EmployeeModel.__table__.c.roles.type.item_type is employee_role_type
    assert InvitationModel.__table__.c.roles.type.item_type is employee_role_type
    assert InvitationModel.__table__.c.status.type.enum_class is InvitationStatus
