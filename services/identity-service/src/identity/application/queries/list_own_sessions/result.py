from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OwnSessionDTO:
    session_id: UUID
    created_at: datetime
    expires_at: datetime
    is_current: bool


@dataclass(frozen=True, slots=True)
class ListOwnSessionsResult:
    sessions: tuple[OwnSessionDTO, ...]
