import hashlib
import hmac
import secrets

from identity.application.ports.security.client_credentials import IssuedClientSecret
from identity.domain.value_objects.service_account import ClientId, ClientSecretHash

_HASH_PREFIX = "hmac-sha256$"
_SECRET_PREFIX = "fgs_"
_MAX_SECRET_LENGTH = 256


class HmacClientCredentials:
    def __init__(self, hash_key: bytes) -> None:
        if not isinstance(hash_key, bytes) or len(hash_key) < 32:
            raise ValueError("Client secret hash key must contain at least 32 bytes")
        self._hash_key = hash_key

    def new_client_id(self) -> ClientId:
        return ClientId("sa_" + secrets.token_hex(16))

    def issue_secret(self) -> IssuedClientSecret:
        plain_secret = _SECRET_PREFIX + secrets.token_urlsafe(32)
        return IssuedClientSecret(
            plain_secret=plain_secret,
            secret_hash=self._hash(plain_secret),
        )

    def matches(self, plain_secret: str, secret_hash: ClientSecretHash) -> bool:
        if not isinstance(secret_hash, ClientSecretHash):
            raise TypeError("secret_hash must be ClientSecretHash")
        if not isinstance(plain_secret, str) or not plain_secret:
            return False
        if len(plain_secret) > _MAX_SECRET_LENGTH:
            return False
        return hmac.compare_digest(
            self._hash(plain_secret).value.encode("ascii"),
            secret_hash.value.encode("utf-8"),
        )

    def _hash(self, plain_secret: str) -> ClientSecretHash:
        digest = hmac.new(
            self._hash_key, plain_secret.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return ClientSecretHash(_HASH_PREFIX + digest)
