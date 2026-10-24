from dataclasses import dataclass

from identity.domain.enums.role import EmployeeRole
from identity.domain.events.base import DomainEvent
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId


@dataclass(frozen=True, slots=True, kw_only=True)
class EmailChanged(DomainEvent):
    employee_id: EmployeeId
    new_email: Email


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeInvited(DomainEvent):
    employee_id: EmployeeId
    email: Email


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeActivated(DomainEvent):
    employee_id: EmployeeId


@dataclass(frozen=True, slots=True, kw_only=True)
class PasswordChanged(DomainEvent):
    employee_id: EmployeeId


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeBlocked(DomainEvent):
    employee_id: EmployeeId


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeUnblocked(DomainEvent):
    employee_id: EmployeeId


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeDeactivated(DomainEvent):
    employee_id: EmployeeId


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeRoleAssigned(DomainEvent):
    employee_id: EmployeeId
    role: EmployeeRole


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeeRoleRevoked(DomainEvent):
    employee_id: EmployeeId
    role: EmployeeRole
