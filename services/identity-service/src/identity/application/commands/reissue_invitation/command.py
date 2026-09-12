from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReissueInvitationCommand:
    inviter_id: UUID
    employee_email: str
