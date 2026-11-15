from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt

from identity.application.exceptions import AuthenticationError
from identity.application.ports.clock import Clock
from identity.application.ports.security.machine_token_issuer import (
    IssuedMachineToken,
)
from identity.application.ports.security.machine_token_verifier import (
    MachineTokenClaims,
)
from identity.domain.enums.scope import MachineScope
from identity.domain.exceptions import ServiceAccountValidationError
from identity.domain.value_objects.service_account import ClientId, ServiceAccountId

_TOKEN_USE = "machine"
_REQUIRED_CLAIMS = ["iss", "aud", "sub", "said", "scope", "iat", "exp", "jti"]


class JwtMachineTokens:
    def __init__(
        self,
        signing_key: bytes,
        lifetime: timedelta,
        issuer: str,
        audience: str,
        clock: Clock,
    ) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("Machine token signing key must contain at least 32 bytes")
        if not isinstance(lifetime, timedelta) or lifetime < timedelta(seconds=1):
            raise ValueError("Machine token lifetime must be at least one second")
        if lifetime > timedelta(hours=1):
            raise ValueError("Machine token lifetime must not exceed one hour")
        if not isinstance(issuer, str) or not issuer:
            raise ValueError("Machine token issuer must not be empty")
        if not isinstance(audience, str) or not audience:
            raise ValueError("Machine token audience must not be empty")

        self._signing_key = signing_key
        self._lifetime = lifetime
        self._issuer = issuer
        self._audience = audience
        self._clock = clock

    def issue(
        self,
        *,
        service_account_id: ServiceAccountId,
        client_id: ClientId,
        scopes: frozenset[MachineScope],
        issued_at: datetime,
    ) -> IssuedMachineToken:
        if not isinstance(service_account_id, ServiceAccountId):
            raise TypeError("service_account_id must be ServiceAccountId")
        if not isinstance(client_id, ClientId):
            raise TypeError("client_id must be ClientId")
        if not isinstance(scopes, frozenset) or not scopes:
            raise ValueError("Machine token scopes must not be empty")
        if any(not isinstance(scope, MachineScope) for scope in scopes):
            raise TypeError("scopes must contain only MachineScope values")
        if not isinstance(issued_at, datetime) or issued_at.utcoffset() is None:
            raise ValueError("issued_at must be timezone-aware")

        issued_at_timestamp = int(issued_at.timestamp())
        expires_at_timestamp = int((issued_at + self._lifetime).timestamp())
        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": client_id.value,
            "said": str(service_account_id.value),
            "scope": " ".join(sorted(scope.value for scope in scopes)),
            "iat": issued_at_timestamp,
            "exp": expires_at_timestamp,
            "jti": str(uuid4()),
            "token_use": _TOKEN_USE,
        }
        return IssuedMachineToken(
            plain_token=jwt.encode(payload, self._signing_key, algorithm="HS256"),
            expires_at=datetime.fromtimestamp(expires_at_timestamp, timezone.utc),
        )

    def verify(self, access_token: str) -> MachineTokenClaims:
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
                    "require": [*_REQUIRED_CLAIMS, "token_use"],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            if payload["token_use"] != _TOKEN_USE:
                raise ValueError("Wrong token use")
            if type(payload["iat"]) is not int or type(payload["exp"]) is not int:
                raise ValueError("Invalid token timestamps")
            if payload["exp"] <= payload["iat"]:
                raise ValueError("Invalid token lifetime")
            expires_at = datetime.fromtimestamp(payload["exp"], timezone.utc)
            if expires_at <= self._clock.now():
                raise ValueError("Token expired")

            scope_value = payload["scope"]
            if not isinstance(scope_value, str) or not scope_value.strip():
                raise ValueError("Invalid token scope")
            scope_values = scope_value.split(" ")
            scopes = frozenset(MachineScope(value) for value in scope_values)
            if len(scopes) != len(scope_values):
                raise ValueError("Duplicate token scopes")
            if not isinstance(payload["sub"], str) or not isinstance(
                payload["said"], str
            ):
                raise TypeError("Invalid token subject")

            return MachineTokenClaims(
                service_account_id=ServiceAccountId(UUID(payload["said"])),
                client_id=ClientId(payload["sub"]),
                scopes=scopes,
                expires_at=expires_at,
            )
        except (
            jwt.InvalidTokenError,
            TypeError,
            ValueError,
            OverflowError,
            OSError,
            UnicodeError,
            ServiceAccountValidationError,
        ) as error:
            raise AuthenticationError("Invalid access token") from error
