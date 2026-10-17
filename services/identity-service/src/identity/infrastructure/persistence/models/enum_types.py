from sqlalchemy import Enum

from identity.domain.enums.role import EmployeeRole
from identity.infrastructure.persistence.models.base import Base


employee_role_type = Enum(
    EmployeeRole,
    name="employee_role",
    metadata=Base.metadata,
    native_enum=True,
    validate_strings=True,
)
