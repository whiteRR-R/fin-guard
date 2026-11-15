from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from identity.domain.enums.scope import MachineScope
from identity.domain.enums.status import ServiceAccountStatus


class CreateServiceAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    scopes: tuple[MachineScope, ...] = Field(min_length=1)


class CreatedServiceAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_account_id: UUID
    client_id: str
    client_secret: str
    scopes: tuple[MachineScope, ...]
    created_at: datetime


class RotatedClientSecretResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_account_id: UUID
    client_id: str
    client_secret: str
    previous_secret_expires_at: datetime | None


class ClientSecretResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    secret_id: UUID
    created_at: datetime
    expires_at: datetime | None


class ServiceAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_account_id: UUID
    client_id: str
    name: str
    scopes: tuple[MachineScope, ...]
    status: ServiceAccountStatus
    created_by: UUID
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None
    active_secrets: tuple[ClientSecretResponse, ...]


class ServiceAccountPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_accounts: tuple[ServiceAccountResponse, ...]
    limit: int
    offset: int
    has_more: bool


class MachineAccessTokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    scope: str


class OAuthErrorResponse(BaseModel):
    error: str
