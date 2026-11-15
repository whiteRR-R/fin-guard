from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from identity.infrastructure.persistence.models.base import Base


class RateLimitCounterModel(Base):
    __tablename__ = "rate_limit_counter"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    hits: Mapped[int] = mapped_column(Integer, nullable=False)
