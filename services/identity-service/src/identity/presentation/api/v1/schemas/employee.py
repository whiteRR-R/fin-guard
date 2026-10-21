from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, SecretStr

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    email: EmailStr
    status: EmployeeStatus
    roles: tuple[EmployeeRole, ...]


class EmployeePageResponse(BaseModel):
    employees: tuple[EmployeeResponse, ...]
    limit: int
    offset: int
    has_more: bool


class EmployeeStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    status: EmployeeStatus


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    password: SecretStr


class ChangePasswordRequest(BaseModel):
    current_password: SecretStr
    new_password: SecretStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    refresh_token_expires_at: datetime
    token_type: str = "bearer"
