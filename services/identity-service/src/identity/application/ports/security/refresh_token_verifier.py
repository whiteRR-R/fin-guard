from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)


@dataclass(frozen=True, kw_only=True, slots=True)
class RefreshTokenClaims:
    session_id: RefreshSessionId
    expires_at: datetime


class RefreshTokenVerifier(Protocol):
    def verify(self, refresh_token: str) -> RefreshTokenClaims: ...

    def matches_hash(
        self, refresh_token: str, hashed_token: RefreshTokenHash
    ) -> bool: ...
