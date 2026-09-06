from dataclasses import dataclass

from identity.domain.events.base import DomainEvent
from identity.domain.value_objects.invitation_id import InvitationId


@dataclass(frozen=True, slots=True, kw_only=True)
class InvitationAccepted(DomainEvent):
    invitation_id: InvitationId


@dataclass(frozen=True, slots=True, kw_only=True)
class InvitationRevoked(DomainEvent):
    invitation_id: InvitationId
