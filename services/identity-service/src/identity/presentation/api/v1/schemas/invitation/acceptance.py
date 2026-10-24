from pydantic import BaseModel, SecretStr


class AcceptInvitationRequest(BaseModel):
    token: SecretStr
    password: SecretStr
