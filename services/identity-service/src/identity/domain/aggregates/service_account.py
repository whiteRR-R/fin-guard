from collections.abc import Iterable
from datetime import datetime, timedelta

from identity.domain.enums.scope import MachineScope
from identity.domain.enums.status import ServiceAccountStatus
from identity.domain.events.base import DomainEvent
from identity.domain.events.service_account import (
    ClientSecretRotated,
    ServiceAccountCreated,
    ServiceAccountRevoked,
)
from identity.domain.exceptions import (
    InvalidServiceAccountStateError,
    ScopeNotGrantedError,
    ServiceAccountRevokedError,
    ServiceAccountValidationError,
)
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.service_account import (
    ClientId,
    ClientSecretHash,
    ClientSecretId,
    ServiceAccountId,
    ServiceAccountName,
)

MAX_ROTATION_GRACE_PERIOD = timedelta(days=7)

USAGE_RECORD_INTERVAL = timedelta(minutes=1)


def _ensure_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ServiceAccountValidationError(f"{name} must be timezone-aware")


class ClientSecret:
    def __init__(
        self,
        *,
        secret_id: ClientSecretId,
        secret_hash: ClientSecretHash,
        created_at: datetime,
        expires_at: datetime | None,
        revoked_at: datetime | None,
    ) -> None:
        if not isinstance(secret_id, ClientSecretId):
            raise TypeError("secret_id must be ClientSecretId")
        if not isinstance(secret_hash, ClientSecretHash):
            raise TypeError("secret_hash must be ClientSecretHash")
        _ensure_aware(created_at, "created_at")
        if expires_at is not None:
            _ensure_aware(expires_at, "expires_at")
            if expires_at < created_at:
                raise ServiceAccountValidationError(
                    "Secret expiration cannot be before creation"
                )
        if revoked_at is not None:
            _ensure_aware(revoked_at, "revoked_at")
            if revoked_at < created_at:
                raise ServiceAccountValidationError(
                    "Secret revocation cannot be before creation"
                )

        self._id = secret_id
        self._hash = secret_hash
        self._created_at = created_at
        self._expires_at = expires_at
        self._revoked_at = revoked_at

    def __repr__(self) -> str:
        return (
            f"ClientSecret(id={self._id.value}, created_at={self._created_at!r}, "
            f"expires_at={self._expires_at!r}, revoked_at={self._revoked_at!r})"
        )

    @property
    def id(self) -> ClientSecretId:
        return self._id

    @property
    def secret_hash(self) -> ClientSecretHash:
        return self._hash

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def expires_at(self) -> datetime | None:
        return self._expires_at

    @property
    def revoked_at(self) -> datetime | None:
        return self._revoked_at

    @property
    def is_current(self) -> bool:
        return self._expires_at is None and self._revoked_at is None

    def is_active(self, now: datetime) -> bool:
        if self._revoked_at is not None:
            return False
        return self._expires_at is None or now < self._expires_at

    def _expire_at(self, moment: datetime) -> None:
        self._expires_at = moment

    def _revoke(self, now: datetime) -> None:
        if self._revoked_at is None:
            self._revoked_at = now


class ServiceAccount:
    def __init__(
        self,
        *,
        service_account_id: ServiceAccountId,
        client_id: ClientId,
        name: ServiceAccountName,
        scopes: Iterable[MachineScope],
        status: ServiceAccountStatus,
        secrets: Iterable[ClientSecret],
        created_by: EmployeeId,
        created_at: datetime,
        revoked_at: datetime | None,
        last_used_at: datetime | None,
    ) -> None:
        if not isinstance(service_account_id, ServiceAccountId):
            raise TypeError("service_account_id must be ServiceAccountId")
        if not isinstance(client_id, ClientId):
            raise TypeError("client_id must be ClientId")
        if not isinstance(name, ServiceAccountName):
            raise TypeError("name must be ServiceAccountName")
        if not isinstance(status, ServiceAccountStatus):
            raise TypeError("status must be ServiceAccountStatus")
        if not isinstance(created_by, EmployeeId):
            raise TypeError("created_by must be EmployeeId")
        _ensure_aware(created_at, "created_at")
        if last_used_at is not None:
            _ensure_aware(last_used_at, "last_used_at")

        normalized_scopes = self._normalize_scopes(scopes)
        secret_list = list(secrets)
        if any(not isinstance(secret, ClientSecret) for secret in secret_list):
            raise TypeError("secrets must contain only ClientSecret values")
        if len({secret.id for secret in secret_list}) != len(secret_list):
            raise ServiceAccountValidationError("Secret identifiers must be unique")

        current = [secret for secret in secret_list if secret.is_current]
        if status is ServiceAccountStatus.ACTIVE:
            if revoked_at is not None:
                raise InvalidServiceAccountStateError(
                    "Active service account cannot have revoked_at"
                )
            if len(current) != 1:
                raise InvalidServiceAccountStateError(
                    "Active service account must have exactly one current secret"
                )
        else:
            if revoked_at is None:
                raise InvalidServiceAccountStateError(
                    "Revoked service account must have revoked_at"
                )
            _ensure_aware(revoked_at, "revoked_at")
            if revoked_at < created_at:
                raise InvalidServiceAccountStateError(
                    "Revocation cannot be before creation"
                )
            if current:
                raise InvalidServiceAccountStateError(
                    "Revoked service account cannot have a current secret"
                )

        self._id = service_account_id
        self._client_id = client_id
        self._name = name
        self._scopes = normalized_scopes
        self._status = status
        self._secrets = secret_list
        self._created_by = created_by
        self._created_at = created_at
        self._revoked_at = revoked_at
        self._last_used_at = last_used_at
        self._events: list[DomainEvent] = []

    @classmethod
    def create(
        cls,
        *,
        service_account_id: ServiceAccountId,
        client_id: ClientId,
        name: ServiceAccountName,
        scopes: Iterable[MachineScope],
        created_by: EmployeeId,
        secret_id: ClientSecretId,
        secret_hash: ClientSecretHash,
        created_at: datetime,
    ) -> "ServiceAccount":
        account = cls(
            service_account_id=service_account_id,
            client_id=client_id,
            name=name,
            scopes=scopes,
            status=ServiceAccountStatus.ACTIVE,
            secrets=(
                ClientSecret(
                    secret_id=secret_id,
                    secret_hash=secret_hash,
                    created_at=created_at,
                    expires_at=None,
                    revoked_at=None,
                ),
            ),
            created_by=created_by,
            created_at=created_at,
            revoked_at=None,
            last_used_at=None,
        )
        account._record_event(
            ServiceAccountCreated(
                service_account_id=service_account_id,
                client_id=client_id,
                scopes=account.scopes,
            )
        )
        return account

    @classmethod
    def restore(
        cls,
        *,
        service_account_id: ServiceAccountId,
        client_id: ClientId,
        name: ServiceAccountName,
        scopes: Iterable[MachineScope],
        status: ServiceAccountStatus,
        secrets: Iterable[ClientSecret],
        created_by: EmployeeId,
        created_at: datetime,
        revoked_at: datetime | None,
        last_used_at: datetime | None,
    ) -> "ServiceAccount":
        return cls(
            service_account_id=service_account_id,
            client_id=client_id,
            name=name,
            scopes=scopes,
            status=status,
            secrets=secrets,
            created_by=created_by,
            created_at=created_at,
            revoked_at=revoked_at,
            last_used_at=last_used_at,
        )

    @property
    def id(self) -> ServiceAccountId:
        return self._id

    @property
    def client_id(self) -> ClientId:
        return self._client_id

    @property
    def name(self) -> ServiceAccountName:
        return self._name

    @property
    def scopes(self) -> frozenset[MachineScope]:
        return self._scopes

    @property
    def status(self) -> ServiceAccountStatus:
        return self._status

    @property
    def secrets(self) -> tuple[ClientSecret, ...]:
        return tuple(self._secrets)

    @property
    def created_by(self) -> EmployeeId:
        return self._created_by

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def revoked_at(self) -> datetime | None:
        return self._revoked_at

    @property
    def last_used_at(self) -> datetime | None:
        return self._last_used_at

    def active_secrets(self, now: datetime) -> tuple[ClientSecret, ...]:
        _ensure_aware(now, "now")
        if self._status is not ServiceAccountStatus.ACTIVE:
            return ()
        return tuple(secret for secret in self._secrets if secret.is_active(now))

    def can_authenticate(self, now: datetime) -> bool:
        return bool(self.active_secrets(now))

    def rotate_secret(
        self,
        *,
        secret_id: ClientSecretId,
        secret_hash: ClientSecretHash,
        now: datetime,
        grace_period: timedelta,
    ) -> ClientSecret | None:
        self._ensure_active()
        _ensure_aware(now, "now")
        if not isinstance(grace_period, timedelta):
            raise TypeError("grace_period must be timedelta")
        if grace_period < timedelta(0) or grace_period > MAX_ROTATION_GRACE_PERIOD:
            raise ServiceAccountValidationError(
                "Grace period must be between zero and seven days"
            )
        if any(secret.id == secret_id for secret in self._secrets):
            raise ServiceAccountValidationError("Secret identifier already exists")

        previous: ClientSecret | None = None
        for secret in self._secrets:
            if secret.is_current:
                if grace_period > timedelta(0):
                    secret._expire_at(now + grace_period)
                    previous = secret
                else:
                    secret._revoke(now)
            elif secret.is_active(now):
                secret._revoke(now)

        self._secrets = [secret for secret in self._secrets if secret.is_active(now)]
        self._secrets.append(
            ClientSecret(
                secret_id=secret_id,
                secret_hash=secret_hash,
                created_at=now,
                expires_at=None,
                revoked_at=None,
            )
        )
        self._record_event(ClientSecretRotated(service_account_id=self._id))
        return previous

    def revoke(self, now: datetime) -> None:
        self._ensure_active()
        _ensure_aware(now, "now")
        if now < self._created_at:
            raise InvalidServiceAccountStateError(
                "Revocation cannot be before creation"
            )
        for secret in self._secrets:
            secret._revoke(now)
        self._status = ServiceAccountStatus.REVOKED
        self._revoked_at = now
        self._record_event(ServiceAccountRevoked(service_account_id=self._id))

    def authorize_scopes(
        self, requested: Iterable[MachineScope] | None
    ) -> frozenset[MachineScope]:
        self._ensure_active()
        if requested is None:
            return self._scopes
        requested_scopes = frozenset(requested)
        if not requested_scopes:
            return self._scopes
        if any(not isinstance(scope, MachineScope) for scope in requested_scopes):
            raise TypeError("requested scopes must be MachineScope values")
        if not requested_scopes <= self._scopes:
            raise ScopeNotGrantedError("Requested scope is not granted")
        return requested_scopes

    def record_usage(self, now: datetime) -> bool:
        self._ensure_active()
        _ensure_aware(now, "now")
        if (
            self._last_used_at is not None
            and now - self._last_used_at < USAGE_RECORD_INTERVAL
        ):
            return False
        self._last_used_at = now
        return True

    def pull_events(self) -> tuple[DomainEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    def _record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def _ensure_active(self) -> None:
        if self._status is ServiceAccountStatus.REVOKED:
            raise ServiceAccountRevokedError("Service account is revoked")

    @staticmethod
    def _normalize_scopes(scopes: Iterable[MachineScope]) -> frozenset[MachineScope]:
        if isinstance(scopes, (str, bytes)):
            raise TypeError("scopes must be an iterable of MachineScope")
        try:
            normalized = frozenset(scopes)
        except TypeError as error:
            raise TypeError("scopes must be an iterable of MachineScope") from error
        if not normalized:
            raise ServiceAccountValidationError(
                "Service account must have at least one scope"
            )
        if any(not isinstance(scope, MachineScope) for scope in normalized):
            raise TypeError("scopes must contain only MachineScope values")
        return normalized
