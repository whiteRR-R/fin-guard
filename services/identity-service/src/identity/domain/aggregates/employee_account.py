from collections.abc import Iterable

from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.events.base import DomainEvent
from identity.domain.events.employee import (
    EmailChanged,
    EmployeeActivated,
    EmployeeBlocked,
    EmployeeDeactivated,
    EmployeeInvited,
    EmployeeRoleAssigned,
    EmployeeRoleRevoked,
    EmployeeUnblocked,
    PasswordChanged,
)
from identity.domain.exceptions import (
    EmployeeIsBlockedError,
    EmployeeIsDeactivatedError,
    EmployeeIsInvitedError,
    EmployeeIsNotInvitedError,
    EmployeeRoleError,
    EmployeeStatusError,
)
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import HashedPassword


class EmployeeAccount:
    def __init__(
        self,
        *,
        employee_id: EmployeeId,
        email: Email,
        password_hash: HashedPassword | None,
        roles: Iterable[EmployeeRole],
        status: EmployeeStatus,
    ) -> None:
        normalized_roles = self._normalize_roles(roles)
        self._validate_state(
            employee_id=employee_id,
            email=email,
            password_hash=password_hash,
            roles=normalized_roles,
            status=status,
        )

        self._employee_id = employee_id
        self._email = email
        self._password_hash = password_hash
        self._roles = normalized_roles
        self._status = status
        self._events: list[DomainEvent] = []

    @classmethod
    def invite(
        cls,
        *,
        employee_id: EmployeeId,
        email: Email,
        roles: Iterable[EmployeeRole],
    ) -> "EmployeeAccount":
        employee = cls(
            employee_id=employee_id,
            email=email,
            password_hash=None,
            roles=roles,
            status=EmployeeStatus.INVITED,
        )
        employee._record_event(
            EmployeeInvited(employee_id=employee_id, email=email)
        )
        return employee

    @classmethod
    def restore(
        cls,
        *,
        employee_id: EmployeeId,
        email: Email,
        password_hash: HashedPassword | None,
        roles: Iterable[EmployeeRole],
        status: EmployeeStatus,
    ) -> "EmployeeAccount":
        return cls(
            employee_id=employee_id,
            email=email,
            password_hash=password_hash,
            roles=roles,
            status=status,
        )

    @property
    def id(self) -> EmployeeId:
        return self._employee_id

    @property
    def email(self) -> Email:
        return self._email

    @property
    def password_hash(self) -> HashedPassword | None:
        return self._password_hash

    @property
    def roles(self) -> frozenset[EmployeeRole]:
        return self._roles

    @property
    def status(self) -> EmployeeStatus:
        return self._status

    def activate(self, password_hash: HashedPassword) -> None:
        if self._status is not EmployeeStatus.INVITED:
            raise EmployeeIsNotInvitedError("Only invited employee can be activated")

        if not isinstance(password_hash, HashedPassword):
            raise TypeError("password_hash must be HashedPassword")

        self._password_hash = password_hash
        self._status = EmployeeStatus.ACTIVE
        self._record_event(EmployeeActivated(employee_id=self._employee_id))

    def deactivate(self) -> None:
        if self._status is EmployeeStatus.DEACTIVATED:
            raise EmployeeIsDeactivatedError("Employee is already deactivated")

        if self._status is EmployeeStatus.INVITED:
            raise EmployeeStatusError("Invited employee cannot be deactivated")

        self._status = EmployeeStatus.DEACTIVATED
        self._record_event(EmployeeDeactivated(employee_id=self._employee_id))

    def assign_role(self, role: EmployeeRole) -> None:
        self._ensure_not_deactivated("assign role")
        self._ensure_role_type(role)

        if role in self._roles:
            return

        self._roles = self._roles | {role}
        self._record_event(
            EmployeeRoleAssigned(employee_id=self._employee_id, role=role)
        )

    def revoke_role(self, role: EmployeeRole) -> None:
        self._ensure_not_deactivated("revoke role")
        self._ensure_role_type(role)

        if role not in self._roles:
            return

        if len(self._roles) == 1:
            raise EmployeeRoleError("Employee must have at least one role")

        self._roles = self._roles - {role}
        self._record_event(
            EmployeeRoleRevoked(employee_id=self._employee_id, role=role)
        )

    def change_email(self, new_email: Email) -> None:
        self._ensure_active("change email")

        if not isinstance(new_email, Email):
            raise TypeError("new_email must be Email")

        if self._email == new_email:
            return

        self._email = new_email
        self._record_event(
            EmailChanged(employee_id=self._employee_id, new_email=self._email)
        )

    def change_password(self, new_password_hash: HashedPassword) -> None:
        self._ensure_active("change password")

        if not isinstance(new_password_hash, HashedPassword):
            raise TypeError("new_password_hash must be HashedPassword")

        if self._password_hash == new_password_hash:
            return

        self._password_hash = new_password_hash
        self._record_event(PasswordChanged(employee_id=self._employee_id))

    def block(self) -> None:
        if self._status is not EmployeeStatus.ACTIVE:
            raise EmployeeStatusError("Only active employee can be blocked")

        self._status = EmployeeStatus.BLOCKED
        self._record_event(EmployeeBlocked(employee_id=self._employee_id))

    def unblock(self) -> None:
        if self._status is not EmployeeStatus.BLOCKED:
            raise EmployeeStatusError("Only blocked employee can be unblocked")

        self._status = EmployeeStatus.ACTIVE
        self._record_event(EmployeeUnblocked(employee_id=self._employee_id))

    def pull_events(self) -> tuple[DomainEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    def _record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def _ensure_active(self, operation: str) -> None:
        if self._status is EmployeeStatus.INVITED:
            raise EmployeeIsInvitedError(f"Invited employee cannot {operation}")

        if self._status is EmployeeStatus.DEACTIVATED:
            raise EmployeeIsDeactivatedError(
                f"Deactivated employee cannot {operation}"
            )

        if self._status is EmployeeStatus.BLOCKED:
            raise EmployeeIsBlockedError(f"Blocked employee cannot {operation}")

    def _ensure_not_deactivated(self, operation: str) -> None:
        if self._status is EmployeeStatus.DEACTIVATED:
            raise EmployeeIsDeactivatedError(
                f"Deactivated employee cannot {operation}"
            )

    @staticmethod
    def _ensure_role_type(role: EmployeeRole) -> None:
        if not isinstance(role, EmployeeRole):
            raise TypeError("role must be EmployeeRole")

    @classmethod
    def _normalize_roles(
        cls,
        roles: Iterable[EmployeeRole],
    ) -> frozenset[EmployeeRole]:
        if isinstance(roles, (str, bytes)):
            raise TypeError("roles must be an iterable of EmployeeRole")

        try:
            normalized_roles = frozenset(roles)
        except TypeError as error:
            raise TypeError("roles must be an iterable of EmployeeRole") from error

        if not normalized_roles:
            raise EmployeeRoleError("Employee must have at least one role")

        for role in normalized_roles:
            cls._ensure_role_type(role)

        return normalized_roles

    @classmethod
    def _validate_state(
        cls,
        *,
        employee_id: EmployeeId,
        email: Email,
        password_hash: HashedPassword | None,
        roles: frozenset[EmployeeRole],
        status: EmployeeStatus,
    ) -> None:
        if not isinstance(employee_id, EmployeeId):
            raise TypeError("employee_id must be EmployeeId")

        if not isinstance(email, Email):
            raise TypeError("email must be Email")

        if not isinstance(status, EmployeeStatus):
            raise TypeError("status must be EmployeeStatus")

        if status is EmployeeStatus.INVITED:
            if password_hash is not None:
                raise EmployeeStatusError(
                    "Invited employee must not have a password hash"
                )
            return

        if not isinstance(password_hash, HashedPassword):
            raise EmployeeStatusError(
                "Active, blocked or deactivated employee must have a password hash"
            )
