from collections.abc import Iterable
from datetime import datetime

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import InvitationStatus
from identity.domain.events.base import DomainEvent
from identity.domain.events.invitation import InvitationAccepted, InvitationRevoked
from identity.domain.exceptions import (
    InvalidInvitationPeriodError,
    InvalidInvitationStatusError,
    InvitationAlreadyAcceptedError,
    InvitationExpiredError,
    InvitationRevokedError,
)
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash


class Invitation:
    def __init__(
        self,
        *,
        invitation_id: InvitationId,
        invited_by: EmployeeId,
        invited_email: Email,
        roles: Iterable[EmployeeRole],
        status: InvitationStatus,
        token_hash: InvitationTokenHash,
        created_at: datetime,
        expires_at: datetime,
        accepted_at: datetime | None,
        revoked_at: datetime | None,
    ) -> None:
        normalized_roles = self._normalize_roles(roles)
        self._validate_state(
            invitation_id=invitation_id,
            invited_by=invited_by,
            invited_email=invited_email,
            status=status,
            token_hash=token_hash,
            created_at=created_at,
            expires_at=expires_at,
            accepted_at=accepted_at,
            revoked_at=revoked_at,
        )

        self._invitation_id = invitation_id
        self._invited_by = invited_by
        self._invited_email = invited_email
        self._roles = normalized_roles
        self._status = status
        self._token_hash = token_hash
        self._created_at = created_at
        self._expires_at = expires_at
        self._accepted_at = accepted_at
        self._revoked_at = revoked_at
        self._events: list[DomainEvent] = []

    @classmethod
    def issue(
        cls,
        *,
        invitation_id: InvitationId,
        invited_email: Email,
        roles: Iterable[EmployeeRole],
        invited_by: EmployeeId,
        token_hash: InvitationTokenHash,
        created_at: datetime,
        expires_at: datetime,
    ) -> "Invitation":
        return cls(
            invitation_id=invitation_id,
            invited_by=invited_by,
            invited_email=invited_email,
            roles=roles,
            status=InvitationStatus.PENDING,
            token_hash=token_hash,
            created_at=created_at,
            expires_at=expires_at,
            accepted_at=None,
            revoked_at=None,
        )

    @classmethod
    def restore(
        cls,
        *,
        invitation_id: InvitationId,
        invited_by: EmployeeId,
        invited_email: Email,
        roles: Iterable[EmployeeRole],
        status: InvitationStatus,
        token_hash: InvitationTokenHash,
        created_at: datetime,
        expires_at: datetime,
        accepted_at: datetime | None,
        revoked_at: datetime | None,
    ) -> "Invitation":
        return cls(
            invitation_id=invitation_id,
            invited_by=invited_by,
            invited_email=invited_email,
            roles=roles,
            status=status,
            token_hash=token_hash,
            created_at=created_at,
            expires_at=expires_at,
            accepted_at=accepted_at,
            revoked_at=revoked_at,
        )

    @property
    def id(self) -> InvitationId:
        return self._invitation_id

    @property
    def invited_by(self) -> EmployeeId:
        return self._invited_by

    @property
    def invited_email(self) -> Email:
        return self._invited_email

    @property
    def roles(self) -> frozenset[EmployeeRole]:
        return self._roles

    @property
    def status(self) -> InvitationStatus:
        return self._status

    @property
    def token_hash(self) -> InvitationTokenHash:
        return self._token_hash

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def expires_at(self) -> datetime:
        return self._expires_at

    @property
    def accepted_at(self) -> datetime | None:
        return self._accepted_at

    @property
    def revoked_at(self) -> datetime | None:
        return self._revoked_at

    def is_expired(self, now: datetime) -> bool:
        self._validate_operation_time(now)
        return now >= self._expires_at
        

    def accept(self, now: datetime) -> None:
        if self._status is InvitationStatus.ACCEPTED:
            raise InvitationAlreadyAcceptedError("Invitation is already accepted")

        if self._status is InvitationStatus.REVOKED:
            raise InvitationRevokedError("Invitation has been revoked")

        if self._status is not InvitationStatus.PENDING:
            raise InvalidInvitationStatusError("Invitation must be pending")

        if self.is_expired(now):
            raise InvitationExpiredError("Invitation has expired")

        self._accepted_at = now
        self._status = InvitationStatus.ACCEPTED
        self._record_event(InvitationAccepted(invitation_id=self._invitation_id))

    def revoke(self, now: datetime) -> None:
        if self._status is InvitationStatus.ACCEPTED:
            raise InvitationAlreadyAcceptedError(
                "Accepted invitation cannot be revoked"
            )

        if self._status is InvitationStatus.REVOKED:
            raise InvitationRevokedError("Invitation is already revoked")

        if self._status is not InvitationStatus.PENDING:
            raise InvalidInvitationStatusError("Invitation must be pending")

        if self.is_expired(now):
            raise InvitationExpiredError("Expired invitation cannot be revoked")

        self._revoked_at = now
        self._status = InvitationStatus.REVOKED
        self._record_event(InvitationRevoked(invitation_id=self._invitation_id))

    def pull_events(self) -> tuple[DomainEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    def _record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def _validate_operation_time(self, now: datetime) -> None:
        self._ensure_aware_datetime(now, "now")
        if now < self._created_at:
            raise InvalidInvitationPeriodError(
                "Operation time cannot be before invitation creation"
            )

    @staticmethod
    def _normalize_roles(
        roles: Iterable[EmployeeRole],
    ) -> frozenset[EmployeeRole]:
        if isinstance(roles, (str, bytes)):
            raise TypeError("roles must be an iterable of EmployeeRole")

        try:
            normalized_roles = frozenset(roles)
        except TypeError as error:
            raise TypeError("roles must be an iterable of EmployeeRole") from error

        if not normalized_roles:
            raise ValueError("Invitation must contain at least one role")

        if any(not isinstance(role, EmployeeRole) for role in normalized_roles):
            raise TypeError("roles must contain only EmployeeRole values")

        return normalized_roles

    @classmethod
    def _validate_state(
        cls,
        *,
        invitation_id: InvitationId,
        invited_by: EmployeeId,
        invited_email: Email,
        status: InvitationStatus,
        token_hash: InvitationTokenHash,
        created_at: datetime,
        expires_at: datetime,
        accepted_at: datetime | None,
        revoked_at: datetime | None,
    ) -> None:
        if not isinstance(invitation_id, InvitationId):
            raise TypeError("invitation_id must be InvitationId")

        if not isinstance(invited_by, EmployeeId):
            raise TypeError("invited_by must be EmployeeId")

        if not isinstance(invited_email, Email):
            raise TypeError("invited_email must be Email")

        if not isinstance(status, InvitationStatus):
            raise TypeError("status must be InvitationStatus")

        if not isinstance(token_hash, InvitationTokenHash):
            raise TypeError("token_hash must be InvitationTokenHash")

        cls._ensure_aware_datetime(created_at, "created_at")
        cls._ensure_aware_datetime(expires_at, "expires_at")
        if expires_at <= created_at:
            raise InvalidInvitationPeriodError(
                "Invitation expiration must be after creation"
            )

        if accepted_at is not None:
            cls._ensure_aware_datetime(accepted_at, "accepted_at")

        if revoked_at is not None:
            cls._ensure_aware_datetime(revoked_at, "revoked_at")

        if status is InvitationStatus.PENDING:
            if accepted_at is not None or revoked_at is not None:
                raise InvalidInvitationStatusError(
                    "Pending invitation cannot have transition timestamps"
                )
            return

        if status is InvitationStatus.ACCEPTED:
            if accepted_at is None or revoked_at is not None:
                raise InvalidInvitationStatusError(
                    "Accepted invitation must have only accepted_at"
                )
            if accepted_at < created_at or accepted_at >= expires_at:
                raise InvalidInvitationPeriodError(
                    "Invitation must be accepted before expiration"
                )
            return

        if status is InvitationStatus.REVOKED:
            if revoked_at is None or accepted_at is not None:
                raise InvalidInvitationStatusError(
                    "Revoked invitation must have only revoked_at"
                )
            if revoked_at < created_at or revoked_at >= expires_at:
                raise InvalidInvitationPeriodError(
                    "Invitation must be revoked before expiration"
                )

    @staticmethod
    def _ensure_aware_datetime(value: datetime, name: str) -> None:
        if not isinstance(value, datetime):
            raise TypeError(f"{name} must be datetime")

        if value.tzinfo is None or value.utcoffset() is None:
            raise InvalidInvitationPeriodError(f"{name} must be timezone-aware")
