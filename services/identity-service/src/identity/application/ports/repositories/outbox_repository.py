from typing import Protocol

from identity.application.messages.base import OutboxMessage


class OutboxRepository(Protocol):
    async def add(self, outbox_message: OutboxMessage): ...
