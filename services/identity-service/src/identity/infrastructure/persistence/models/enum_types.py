
from sqlalchemy import Enum

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.infrastructure.persistence.models.base import Base


employee_role_type = Enum(
    EmployeeRole,
    name="employee_role",
    metadata=Base.metadata,
    native_enum=True,
    validate_strings=True,
)

employee_status_type = Enum(
    EmployeeStatus,
    name="employee_status",
    metadata=Base.metadata,
    native_enum=True,
    validate_strings=True
)

invitation_status_type = Enum(
    InvitationStatus,
    name="invitation_status",
    metadata=Base.metadata,
    native_enum=True,
    validate_strings=True
)
