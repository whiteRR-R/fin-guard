from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, SecretStr


class RefreshAccessTokenRequest(BaseModel):
    refresh_token: SecretStr


class RefreshAccessTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class OwnSessionResponse(BaseModel):
    session_id: UUID
    created_at: datetime
    expires_at: datetime
    is_current: bool


class OwnSessionsResponse(BaseModel):
    sessions: tuple[OwnSessionResponse, ...]
