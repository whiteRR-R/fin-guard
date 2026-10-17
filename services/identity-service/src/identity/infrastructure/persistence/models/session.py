from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from identity.infrastructure.persistence.models.base import Base

if TYPE_CHECKING:
    from identity.infrastructure.persistence.models.employee import EmployeeModel


class SessionModel(Base):
    __tablename__ = "session"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employee.id"),
        nullable=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    employee: Mapped["EmployeeModel"] = relationship(
        "EmployeeModel",
        back_populates="sessions",
    )
