from typing import Protocol

from identity.domain.aggregates.invitation import Invitation
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.invitation_id import InvitationId


class InvitationRepository(Protocol):
    async def get_by_id(self, invitation_id: InvitationId) -> Invitation | None: ...
    
    async def get_latest_by_employee_email(self, email: Email) -> Invitation | None: ...

    async def add(self, invitation: Invitation) -> None: ...

    async def save(self, invitation: Invitation) -> None: ...
