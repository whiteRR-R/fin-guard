from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ARRAY, Enum, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.infrastructure.persistence.models.base import Base
from identity.infrastructure.persistence.models.enum_types import (
    employee_role_type,
    employee_status_type,
)

if TYPE_CHECKING:
    from identity.infrastructure.persistence.models.session import SessionModel


class EmployeeModel(Base):
    __tablename__ = "employee"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    roles: Mapped[list[EmployeeRole]] = mapped_column(
        ARRAY(employee_role_type),
        nullable=False,
    )
    password_hash: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[EmployeeStatus] = mapped_column(
        employee_status_type,
        nullable=False,
    )

    sessions: Mapped[list["SessionModel"]] = relationship(
        "SessionModel",
        back_populates="employee",
    )

Index("uq_employee_email_lower", func.lower(EmployeeModel.email), unique=True)
