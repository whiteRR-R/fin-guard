from typing import Protocol

from identity.domain.value_objects.email import Email


class EmailSender(Protocol):
    async def send(self, email: Email, plain_token: str): ...
