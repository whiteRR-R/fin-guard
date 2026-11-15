from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from identity.domain.enums.scope import MachineScope
from identity.domain.enums.status import ServiceAccountStatus
from identity.infrastructure.persistence.models.base import Base
from identity.infrastructure.persistence.models.enum_types import (
    machine_scope_type,
    service_account_status_type,
)


class ServiceAccountModel(Base):
    __tablename__ = "service_account"
    __table_args__ = (
        CheckConstraint(
            "cardinality(scopes) > 0", name="ck_service_account_scopes_nonempty"
        ),
        CheckConstraint(
            "(status = 'ACTIVE') = (revoked_at IS NULL)",
            name="ck_service_account_revoked_at_matches_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scopes: Mapped[list[MachineScope]] = mapped_column(
        ARRAY(machine_scope_type),
        nullable=False,
    )
    status: Mapped[ServiceAccountStatus] = mapped_column(
        service_account_status_type,
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("employee.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    secrets: Mapped[list["ServiceAccountSecretModel"]] = relationship(
        back_populates="service_account",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ServiceAccountSecretModel.created_at",
    )


class ServiceAccountSecretModel(Base):
    __tablename__ = "service_account_secret"
    __table_args__ = (
        Index(
            "uq_service_account_secret_current",
            "service_account_id",
            unique=True,
            postgresql_where=text("expires_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    service_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("service_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    service_account: Mapped[ServiceAccountModel] = relationship(
        back_populates="secrets",
    )
