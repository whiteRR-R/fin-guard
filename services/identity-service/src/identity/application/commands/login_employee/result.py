from dataclasses import dataclass, field
from datetime import datetime

@dataclass(frozen=True)
class LoginEmployeeResult:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    refresh_token_expires_at: datetime
