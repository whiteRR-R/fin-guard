from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RevokeInvitationCommand:
    actor_id: UUID
    invitation_id: UUID
