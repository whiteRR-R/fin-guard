from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash


@dataclass(frozen=True, slots=True)
class InvitationTokenClaims:
    invitation_id: UUID


class InvitationTokenVerifier(Protocol):
    def parse_verified(self, token: str) -> InvitationTokenClaims:
        ...

    def matches_hash(
        self, plain_token: str, expected_hash: InvitationTokenHash
    ) -> bool: ...
