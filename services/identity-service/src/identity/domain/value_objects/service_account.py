import re
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from identity.domain.exceptions import ServiceAccountValidationError

_CLIENT_ID_PATTERN = re.compile(r"^sa_[A-Za-z0-9]{16,64}$")
_NAME_MAX_LENGTH = 100


@dataclass(frozen=True, slots=True)
class ServiceAccountId:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("ServiceAccountId value must be UUID")

    @classmethod
    def new(cls) -> "ServiceAccountId":
        return cls(uuid4())


@dataclass(frozen=True, slots=True)
class ClientSecretId:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("ClientSecretId value must be UUID")

    @classmethod
    def new(cls) -> "ClientSecretId":
        return cls(uuid4())


@dataclass(frozen=True, slots=True)
class ClientId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _CLIENT_ID_PATTERN.fullmatch(
            self.value
        ):
            raise ServiceAccountValidationError("Invalid client_id format")


@dataclass(frozen=True, slots=True)
class ClientSecretHash:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ServiceAccountValidationError("Client secret hash cannot be empty")


@dataclass(frozen=True, slots=True)
class ServiceAccountName:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ServiceAccountValidationError("Service account name must be text")
        normalized = " ".join(self.value.split())
        if not normalized:
            raise ServiceAccountValidationError("Service account name cannot be empty")
        if len(normalized) > _NAME_MAX_LENGTH:
            raise ServiceAccountValidationError(
                f"Service account name must be at most {_NAME_MAX_LENGTH} characters"
            )
        object.__setattr__(self, "value", normalized)
