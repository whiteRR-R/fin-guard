from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash


@dataclass(frozen=True, slots=True)
class IssuedInvitationToken:
    plain_token: str = field(repr=False)
    token_hash: InvitationTokenHash = field(repr=False)
    expires_at: datetime


class InvitationTokenIssuer(Protocol):
    def issue(
        self,
        invitation_id: InvitationId,
        invited_by: EmployeeId,
        employee_email: Email,
        issued_at: datetime,
    ) -> IssuedInvitationToken: ...
