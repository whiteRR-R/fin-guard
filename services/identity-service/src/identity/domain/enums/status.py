from enum import Enum


class EmployeeStatus(Enum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    DEACTIVATED = "DEACTIVATED"


class InvitationStatus(Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REVOKED = "REVOKED"
