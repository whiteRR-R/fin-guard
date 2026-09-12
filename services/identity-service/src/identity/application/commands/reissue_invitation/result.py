from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReissueInvitationResult:
    invitation_id: UUID
    inviter_id: UUID
    employee_id: UUID
