from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AcceptInvitationCommand:
    token: str = field(repr=False)
    password: str = field(repr=False)
    
