from dataclasses import dataclass
from datetime import datetime

from identity.application.ports.security.access_token_issuer import IssuedAccessToken
from identity.application.ports.security.refresh_token_issuer import (
    IssuedRefreshToken,
)


@dataclass(frozen=True)
class LoginEmployeeResult:
    access_token: IssuedAccessToken
    refresh_token: IssuedRefreshToken
    refresh_token_expires_at: datetime
