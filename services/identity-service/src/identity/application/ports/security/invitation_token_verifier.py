from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InvitationTokenClaims:
    invitation_id: UUID
   
   
    
class InvitationTokenVerifier(Protocol):
    def verify(self, token: str) -> InvitationTokenClaims: ...
