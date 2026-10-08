import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt

from identity.application.exceptions import InvalidRefreshTokenError
from identity.application.ports.clock import Clock
from identity.application.ports.security.refresh_token_issuer import IssuedRefreshToken
from identity.application.ports.security.refresh_token_verifier import (
    RefreshTokenClaims,
)
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)


class JwtRefreshTokens:
    def __init__(
        self,
        signing_key: bytes,
        lifetime: timedelta,
        issuer: str,
        audience: str,
        clock: Clock,
    ) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("Refresh token signing key must contain at least 32 bytes")
        if not isinstance(lifetime, timedelta) or lifetime < timedelta(seconds=1):
            raise ValueError("Refresh token lifetime must be at least one second")
        if not isinstance(issuer, str) or not issuer:
            raise ValueError("Refresh token issuer must not be empty")
        if not isinstance(audience, str) or not audience:
            raise ValueError("Refresh token audience must not be empty")

        self._signing_key = signing_key
        self._lifetime = lifetime
        self._issuer = issuer
        self._audience = audience
        self._clock = clock

    def issue(self, session_id: RefreshSessionId) -> IssuedRefreshToken:
        if not isinstance(session_id, RefreshSessionId):
            raise TypeError("session_id must be RefreshSessionId")

        issued_at = self._clock.now()
        if not isinstance(issued_at, datetime) or issued_at.utcoffset() is None:
            raise ValueError("Clock must return a timezone-aware datetime")

        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sid": str(session_id.value),
            "jti": str(uuid4()),
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + self._lifetime).timestamp()),
            "token_use": "refresh",
        }
        plain_token = jwt.encode(payload, self._signing_key, algorithm="HS256")
        token_hash = RefreshTokenHash(
            hashlib.sha256(plain_token.encode("ascii")).hexdigest()
        )
        return IssuedRefreshToken(plain_token=plain_token, token_hash=token_hash)

    def verify(self, refresh_token: str) -> RefreshTokenClaims:
        if not isinstance(refresh_token, str) or not refresh_token:
            raise InvalidRefreshTokenError("Invalid refresh token")

        try:
            payload = jwt.decode(
                refresh_token,
                self._signing_key,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sid",
                        "jti",
                        "iat",
                        "exp",
                        "token_use",
                    ],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            if payload["token_use"] != "refresh":
                raise ValueError("Wrong token use")
            if type(payload["iat"]) is not int or type(payload["exp"]) is not int:
                raise ValueError("Invalid token timestamps")
            if payload["exp"] <= payload["iat"]:
                raise ValueError("Invalid token lifetime")
            if not isinstance(payload["sid"], str) or not isinstance(
                payload["jti"], str
            ):
                raise ValueError("Invalid token identifier")

            UUID(payload["jti"])
            return RefreshTokenClaims(
                session_id=RefreshSessionId(UUID(payload["sid"])),
                expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc),
            )
        except (
            jwt.InvalidTokenError,
            ValueError,
            OverflowError,
            OSError,
            UnicodeError,
        ) as error:
            raise InvalidRefreshTokenError("Invalid refresh token") from error

    def matches_hash(
        self,
        refresh_token: str,
        hashed_token: RefreshTokenHash,
    ) -> bool:
        if not isinstance(hashed_token, RefreshTokenHash):
            raise TypeError("hashed_token must be RefreshTokenHash")
        if not isinstance(refresh_token, str):
            return False

        try:
            candidate_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
        except UnicodeError:
            return False
        return hmac.compare_digest(
            candidate_hash.encode("ascii"),
            hashed_token.value.encode("utf-8"),
        )
