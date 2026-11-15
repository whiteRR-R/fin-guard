from dataclasses import dataclass

from identity.domain.enums.scope import MachineScope
from identity.domain.events.base import DomainEvent
from identity.domain.value_objects.service_account import (
    ClientId,
    ServiceAccountId,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceAccountCreated(DomainEvent):
    service_account_id: ServiceAccountId
    client_id: ClientId
    scopes: frozenset[MachineScope]


@dataclass(frozen=True, slots=True, kw_only=True)
class ClientSecretRotated(DomainEvent):
    service_account_id: ServiceAccountId


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceAccountRevoked(DomainEvent):
    service_account_id: ServiceAccountId
