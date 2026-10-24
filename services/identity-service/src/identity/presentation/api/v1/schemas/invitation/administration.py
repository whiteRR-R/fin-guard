from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from identity.domain.enums.role import EmployeeRole


class InviteEmployeeRequest(BaseModel):
    email: EmailStr
    roles: tuple[EmployeeRole, ...] = Field(min_length=1)


class InviteEmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invitation_id: UUID
    employee_id: UUID


class ReissueInvitationRequest(BaseModel):
    email: EmailStr


class ReissueInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invitation_id: UUID
    inviter_id: UUID
    employee_id: UUID
