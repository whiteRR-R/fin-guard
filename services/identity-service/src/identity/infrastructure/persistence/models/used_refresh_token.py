from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from identity.infrastructure.persistence.models.base import Base


class UsedRefreshTokenModel(Base):
    __tablename__ = "used_refresh_token"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("session.id"),
        primary_key=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(500),
        primary_key=True,
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
