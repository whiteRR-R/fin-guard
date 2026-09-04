from dataclasses import dataclass, field
from uuid import UUID, uuid4

from identity.domain.exceptions import RefreshTokenValidationError


@dataclass(frozen=True)
class RefreshSessionId:
    value: UUID
    
    @classmethod
    def new(cls) -> "RefreshSessionId":
        return cls(uuid4())


@dataclass(frozen=True, slots=True)
class RefreshTokenHash:
    value: str = field(repr=False)
    
    def __post_init__(self):
        if not self.value:
            raise RefreshTokenValidationError("Refresh token hash cannot be empty")
