from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from identity.infrastructure.persistence.models.base import Base


class OutboxMessageModel(Base):
    __tablename__ = "outbox_message"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_outbox_message_version_positive"),
        Index(
            "ix_outbox_message_pending_created_at",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    message_id: Mapped[UUID] = mapped_column(primary_key=True)
    message_type: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
