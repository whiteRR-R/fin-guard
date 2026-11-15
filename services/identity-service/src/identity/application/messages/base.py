from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar
from uuid import UUID, uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboxMessage:
    message_type: ClassVar[str]

    message_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)

    def __init_subclass__(cls) -> None:
        message_type = cls.__dict__.get("message_type")
        if not isinstance(message_type, str) or not message_type:
            raise TypeError(f"{cls.__name__} must declare a non-empty message_type")
