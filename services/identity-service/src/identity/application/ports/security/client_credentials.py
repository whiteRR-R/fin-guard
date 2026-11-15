from dataclasses import dataclass, field
from typing import Protocol

from identity.domain.value_objects.service_account import ClientId, ClientSecretHash


@dataclass(frozen=True, slots=True)
class IssuedClientSecret:
    plain_secret: str = field(repr=False)
    secret_hash: ClientSecretHash = field(repr=False)


class ClientCredentialsIssuer(Protocol):
    def new_client_id(self) -> ClientId: ...

    def issue_secret(self) -> IssuedClientSecret: ...


class ClientSecretVerifier(Protocol):
    def matches(self, plain_secret: str, secret_hash: ClientSecretHash) -> bool: ...
