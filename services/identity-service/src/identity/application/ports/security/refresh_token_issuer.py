from dataclasses import dataclass, field
from typing import Protocol

from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    token_hash: RefreshTokenHash = field(repr=False)


class RefreshTokenIssuer(Protocol):
    def issue(self, session_id: RefreshSessionId) -> IssuedRefreshToken: ...
