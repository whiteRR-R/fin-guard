from datetime import datetime
from uuid import UUID

from sqlalchemy import ARRAY, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import InvitationStatus
from identity.infrastructure.persistence.models.base import Base
from identity.infrastructure.persistence.models.enum_types import (
    employee_role_type,
    invitation_status_type,
)


class InvitationModel(Base):
    __tablename__ = "invitation"
    __table_args__ = (
        CheckConstraint("cardinality(roles) > 0", name="ck_invitation_roles_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    invited_by: Mapped[UUID] = mapped_column(
        ForeignKey("employee.id"),
        nullable=False,
    )
    invited_email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        index=True,
    )
    roles: Mapped[list[EmployeeRole]] = mapped_column(
        ARRAY(employee_role_type),
        nullable=False,
    )
    status: Mapped[InvitationStatus] = mapped_column(
        invitation_status_type,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
