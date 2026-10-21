from dataclasses import fields
from enum import Enum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.messages.base import OutboxMessage
from identity.infrastructure.persistence.models.outbox_message import OutboxMessageModel


def _json_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, outbox_message: OutboxMessage) -> None:
        payload = {
            field.name: _json_value(getattr(outbox_message, field.name))
            for field in fields(outbox_message)
            if field.name not in {"message_id", "created_at", "version"}
        }
        self._session.add(
            OutboxMessageModel(
                message_id=outbox_message.message_id,
                message_type=type(outbox_message).__name__,
                version=getattr(outbox_message, "version", 1),
                payload=payload,
                created_at=outbox_message.created_at,
                published_at=None,
            )
        )
