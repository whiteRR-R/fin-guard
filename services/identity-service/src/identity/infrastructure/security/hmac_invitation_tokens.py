import base64
import binascii
import hashlib
import hmac
from datetime import datetime, timedelta
from uuid import UUID

from identity.application.exceptions import InvalidInvitationTokenError
from identity.application.ports.security.invitation_token_issuer import (
    IssuedInvitationToken,
)
from identity.application.ports.security.invitation_token_verifier import (
    InvitationTokenClaims,
)
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash


class HmacInvitationTokens:
    def __init__(self, signing_key: bytes, lifetime: timedelta) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("Invitation signing key must contain at least 32 bytes")
        if not isinstance(lifetime, timedelta) or lifetime <= timedelta(0):
            raise ValueError("Invitation token lifetime must be positive")

        self._signing_key = signing_key
        self._lifetime = lifetime

    def issue(
        self,
        invitation_id: InvitationId,
        issued_at: datetime,
    ) -> IssuedInvitationToken:
        plain_token = self.derive_token(invitation_id)
        return IssuedInvitationToken(
            plain_token=plain_token,
            token_hash=self._hash(plain_token),
            expires_at=issued_at + self._lifetime,
        )

    def derive_token(self, invitation_id: InvitationId) -> str:
        if not isinstance(invitation_id, InvitationId):
            raise TypeError("invitation_id must be InvitationId")
        identifier = invitation_id.value.bytes
        signature = hmac.digest(self._signing_key, identifier, "sha256")
        return base64.urlsafe_b64encode(identifier + signature).rstrip(b"=").decode("ascii")

    def parse_verified(self, token: str) -> InvitationTokenClaims:
        if not isinstance(token, str) or not token:
            raise InvalidInvitationTokenError("Invalid invitation token")

        try:
            encoded = token.encode("ascii")
            payload = base64.b64decode(
                encoded + b"=" * (-len(encoded) % 4),
                altchars=b"-_",
                validate=True,
            )
        except (UnicodeEncodeError, binascii.Error, ValueError) as error:
            raise InvalidInvitationTokenError("Invalid invitation token") from error

        if len(payload) != 48:
            raise InvalidInvitationTokenError("Invalid invitation token")

        identifier, signature = payload[:16], payload[16:]
        expected_signature = hmac.digest(self._signing_key, identifier, "sha256")
        if not hmac.compare_digest(signature, expected_signature):
            raise InvalidInvitationTokenError("Invalid invitation token")

        return InvitationTokenClaims(invitation_id=UUID(bytes=identifier))

    def matches_hash(
        self, plain_token: str, expected_hash: InvitationTokenHash
    ) -> bool:
        if not isinstance(expected_hash, InvitationTokenHash):
            raise TypeError("expected_hash must be InvitationTokenHash")
        if not isinstance(plain_token, str):
            return False
        return hmac.compare_digest(
            self._hash(plain_token).value,
            expected_hash.value,
        )

    @staticmethod
    def _hash(token: str) -> InvitationTokenHash:
        return InvitationTokenHash(hashlib.sha256(token.encode("utf-8")).hexdigest())
