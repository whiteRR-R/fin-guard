from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AcceptInvitationCommand:
    token: str
    password: str
    
