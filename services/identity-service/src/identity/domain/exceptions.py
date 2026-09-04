# Base


class DomainException(Exception): ...


# Value-Objects errors


class EmailValidationError(DomainException): ...


class PasswordValidationError(DomainException): ...


class RefreshTokenValidationError(DomainException): ...


# Aggregates errors


class EmployeeStatusError(DomainException): ...


class EmployeeIsBlockedError(DomainException): ...


class EmployeeIsInvitedError(DomainException): ...


class EmployeeIsNotInvitedError(DomainException): ...


class EmployeeIsDeactivatedError(DomainException): ...


class EmployeeRoleError(DomainException): ...


class RefreshSessionError(DomainException): ...


class InvitationExpiredError(DomainException): ...


class InvalidInvitationStatusError(DomainException): ...


class InvitationAlreadyAcceptedError(DomainException): ...


class InvitationRevokedError(DomainException): ...


class InvalidInvitationPeriodError(DomainException): ...


class InvitationTokenHashValidationError(DomainException): ...


# Policies Error
class EmployeeDeletionNotAllowedError(DomainException): ...


class EmployeeBlockNotAllowedError(DomainException): ...


class EmployeeUnblockNotAllowedError(DomainException): ...


class EmployeeInviteNotAllowedError(DomainException): ...
