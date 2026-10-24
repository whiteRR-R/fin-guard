from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from identity.application.exceptions import (
    AccessDeniedError,
    ApplicationException,
    AuthenticationError,
    EmailAlreadyTakenError,
    EmployeeAlreadyInvitedError,
    EmployeeIsNotInvitedError,
    EmployeeNotActiveError,
    EmployeeNotFoundError,
    InvalidCurrentPasswordError,
    InvalidEmailError,
    InvalidEmployeeStateError,
    InvalidPaginationError,
    InvalidPasswordError,
    InvitationCannotBeReissuedError,
    InvitationNotFoundError,
    LastActiveAdminError,
    SessionNotFoundError,
)
from identity.application.exceptions import (
    InvalidInvitationStatusError as ApplicationInvalidInvitationStatusError,
)
from identity.domain.exceptions import (
    DomainException,
    EmailValidationError,
    EmployeeInviteNotAllowedError,
    InvitationExpiredError,
    PasswordValidationError,
)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationException)
    async def application_error(
        request: Request, error: ApplicationException
    ) -> JSONResponse:
        if isinstance(error, AuthenticationError):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        if isinstance(
            error,
            (EmployeeNotFoundError, InvitationNotFoundError, SessionNotFoundError),
        ):
            status_code = 404
        elif isinstance(error, (AccessDeniedError, EmployeeNotActiveError)):
            status_code = 403
        elif isinstance(
            error,
            (
                EmailAlreadyTakenError,
                EmployeeAlreadyInvitedError,
                EmployeeIsNotInvitedError,
                InvalidEmployeeStateError,
                ApplicationInvalidInvitationStatusError,
                InvitationCannotBeReissuedError,
                LastActiveAdminError,
            ),
        ):
            status_code = 409
        elif isinstance(
            error,
            (
                InvalidCurrentPasswordError,
                InvalidEmailError,
                InvalidPaginationError,
                InvalidPasswordError,
            ),
        ):
            status_code = 422
        else:
            status_code = 400
        return JSONResponse(status_code=status_code, content={"detail": str(error)})

    @app.exception_handler(DomainException)
    async def domain_error(request: Request, error: DomainException) -> JSONResponse:
        if isinstance(error, (EmailValidationError, PasswordValidationError)):
            status_code = 422
        elif isinstance(error, EmployeeInviteNotAllowedError):
            status_code = 403
        elif isinstance(error, InvitationExpiredError):
            status_code = 410
        else:
            status_code = 409
        return JSONResponse(status_code=status_code, content={"detail": str(error)})
