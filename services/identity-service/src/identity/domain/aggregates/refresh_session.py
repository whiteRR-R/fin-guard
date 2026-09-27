from datetime import datetime

from identity.domain.exceptions import RefreshSessionError
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)
from identity.domain.value_objects.employee_id import EmployeeId


class RefreshSession:
    def __init__(
        self,
        *,
        session_id: RefreshSessionId,
        employee_id: EmployeeId,
        refresh_token_hash: RefreshTokenHash,
        created_at: datetime,
        expires_at: datetime,
        revoked_at: datetime | None,
    ) -> None:
        self._session_id = session_id
        self._employee_id = employee_id
        self._refresh_token_hash = refresh_token_hash
        self._created_at = created_at
        self._expires_at = expires_at
        self._revoked_at = revoked_at

    @classmethod
    def start(
        cls,
        *,
        session_id: RefreshSessionId,
        employee_id: EmployeeId,
        refresh_token_hash: RefreshTokenHash,
        created_at: datetime,
        expires_at: datetime,
    ) -> "RefreshSession":
        if expires_at <= created_at:
            raise RefreshSessionError("Session expiration must be after creation")

        return cls(
            session_id=session_id,
            employee_id=employee_id,
            refresh_token_hash=refresh_token_hash,
            created_at=created_at,
            expires_at=expires_at,
            revoked_at=None,
        )

    @property
    def id(self) -> RefreshSessionId:
        return self._session_id

    @property
    def employee_id(self) -> EmployeeId:
        return self._employee_id

    @property
    def refresh_token_hash(self) -> RefreshTokenHash:
        return self._refresh_token_hash

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def expires_at(self) -> datetime:
        return self._expires_at

    @property
    def revoked_at(self) -> datetime | None:
        return self._revoked_at

    def is_active(self, now: datetime) -> bool:
        return self._revoked_at is None and self._created_at <= now < self._expires_at

    def revoke(self, now: datetime) -> None:
        if self._revoked_at is None:
            self._revoked_at = now

    def rotate(
        self,
        *,
        new_token_hash: RefreshTokenHash,
        now: datetime,
    ) -> None:
        if not self.is_active(now):
            raise RefreshSessionError("Refresh session is not active")

        self._refresh_token_hash = new_token_hash
