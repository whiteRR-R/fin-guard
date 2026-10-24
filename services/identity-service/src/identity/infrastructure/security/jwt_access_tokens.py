from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from identity.application.exceptions import AuthenticationError
from identity.application.ports.security.access_token_issuer import IssuedAccessToken
from identity.application.ports.security.access_token_verifier import AccessTokenClaims
from identity.domain.enums.role import EmployeeRole
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import RefreshSessionId


class JwtAccessTokens:
    def __init__(
        self,
        signing_key: bytes,
        lifetime: timedelta,
        issuer: str,
        audience: str,
    ) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("Access token signing key must contain at least 32 bytes")
        if not isinstance(lifetime, timedelta) or lifetime < timedelta(seconds=1):
            raise ValueError("Access token lifetime must be at least one second")
        if not isinstance(issuer, str) or not issuer:
            raise ValueError("Access token issuer must not be empty")
        if not isinstance(audience, str) or not audience:
            raise ValueError("Access token audience must not be empty")

        self._signing_key = signing_key
        self._lifetime = lifetime
        self._issuer = issuer
        self._audience = audience

    def issue(
        self,
        employee_id: EmployeeId,
        session_id: RefreshSessionId,
        roles: frozenset[EmployeeRole],
        issued_at: datetime,
    ) -> IssuedAccessToken:
        if not isinstance(employee_id, EmployeeId):
            raise TypeError("employee_id must be EmployeeId")
        if not isinstance(session_id, RefreshSessionId):
            raise TypeError("session_id must be RefreshSessionId")
        if not isinstance(roles, frozenset) or not roles:
            raise ValueError("Access token roles must not be empty")
        if any(not isinstance(role, EmployeeRole) for role in roles):
            raise TypeError("roles must contain only EmployeeRole values")
        if not isinstance(issued_at, datetime) or issued_at.utcoffset() is None:
            raise ValueError("issued_at must be timezone-aware")

        issued_at_timestamp = int(issued_at.timestamp())
        expires_at_timestamp = int((issued_at + self._lifetime).timestamp())
        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(employee_id.value),
            "sid": str(session_id.value),
            "roles": sorted(role.value for role in roles),
            "iat": issued_at_timestamp,
            "exp": expires_at_timestamp,
            "token_use": "access",
        }
        plain_token = jwt.encode(payload, self._signing_key, algorithm="HS256")
        return IssuedAccessToken(
            plain_token=plain_token,
            expires_at=datetime.fromtimestamp(expires_at_timestamp, timezone.utc),
        )

    def verify(self, access_token: str) -> AccessTokenClaims:
        if not isinstance(access_token, str) or not access_token:
            raise AuthenticationError("Invalid access token")

        try:
            payload = jwt.decode(
                access_token,
                self._signing_key,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "sid",
                        "roles",
                        "iat",
                        "exp",
                        "token_use",
                    ],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            if payload["token_use"] != "access":
                raise ValueError("Wrong token use")
            if type(payload["iat"]) is not int or type(payload["exp"]) is not int:
                raise ValueError("Invalid token timestamps")
            if payload["exp"] <= payload["iat"]:
                raise ValueError("Invalid token lifetime")
            if not isinstance(payload["sub"], str) or not isinstance(
                payload["sid"], str
            ):
                raise ValueError("Invalid token subject")  # noqa: TRY004

            role_values = payload["roles"]
            if not isinstance(role_values, list) or not role_values:
                raise ValueError("Invalid token roles")
            if any(not isinstance(value, str) for value in role_values):
                raise ValueError("Invalid token roles")

            roles = frozenset(EmployeeRole(value) for value in role_values)
            if len(roles) != len(role_values):
                raise ValueError("Duplicate token roles")

            return AccessTokenClaims(
                employee_id=EmployeeId(UUID(payload["sub"])),
                sid=RefreshSessionId(UUID(payload["sid"])),
                roles=roles,
                expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc),
            )
        except (
            jwt.InvalidTokenError,
            ValueError,
            OverflowError,
            OSError,
            UnicodeError,
        ) as error:
            raise AuthenticationError("Invalid access token") from error
