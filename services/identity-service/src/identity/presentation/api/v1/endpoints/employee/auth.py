from typing import Annotated

from fastapi import APIRouter, Depends

from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.application.commands.login_employee.command import LoginEmployeeCommand
from identity.application.commands.login_employee.handler import LoginEmployeeHandler
from identity.application.commands.logout.command import LogoutCommand
from identity.application.commands.logout.handler import LogoutHandler
from identity.application.commands.logout_all_sessions.command import (
    LogoutAllSessionsCommand,
)
from identity.application.commands.logout_all_sessions.handler import (
    LogoutAllSessionsHandler,
)
from identity.application.commands.refresh_access_token.command import (
    RefreshAccessTokenCommand,
)
from identity.application.commands.refresh_access_token.handler import (
    RefreshAccessTokenHandler,
)
from identity.application.exceptions import (
    AuthenticationError,
    EmployeeNotActiveError,
    EmployeeNotFoundError,
    SessionIsNotActiveError,
    SessionNotFoundError,
)
from identity.presentation.api.dependencies.employee.authentication import (
    get_actor,
    get_login_handler,
)
from identity.presentation.api.dependencies.employee.sessions import (
    get_logout_all_sessions_handler,
    get_logout_handler,
    get_refresh_access_token_handler,
)
from identity.presentation.api.v1.schemas.employee import LoginRequest, LoginResponse
from identity.presentation.api.v1.schemas.session import (
    RefreshAccessTokenRequest,
    RefreshAccessTokenResponse,
)

router = APIRouter(prefix="/auth", tags=["employee authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    handler: Annotated[LoginEmployeeHandler, Depends(get_login_handler)],
) -> LoginResponse:
    result = await handler.execute(
        LoginEmployeeCommand(
            email=body.email,
            password=body.password.get_secret_value(),
        )
    )
    return LoginResponse.model_validate(result, from_attributes=True)


@router.post("/refresh", response_model=RefreshAccessTokenResponse)
async def refresh_access_token(
    body: RefreshAccessTokenRequest,
    handler: Annotated[
        RefreshAccessTokenHandler, Depends(get_refresh_access_token_handler)
    ],
) -> RefreshAccessTokenResponse:
    try:
        result = await handler.execute(
            RefreshAccessTokenCommand(
                refresh_token=body.refresh_token.get_secret_value()
            )
        )
    except (
        SessionNotFoundError,
        SessionIsNotActiveError,
        EmployeeNotFoundError,
        EmployeeNotActiveError,
    ) as error:
        raise AuthenticationError("Invalid refresh token") from error

    return RefreshAccessTokenResponse.model_validate(result, from_attributes=True)


@router.post("/logout", status_code=204)
async def logout(
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[LogoutHandler, Depends(get_logout_handler)],
) -> None:
    await handler.execute(
        LogoutCommand(
            employee_id=actor.employee_id.value,
            session_id=actor.session_id.value,
        )
    )


@router.post("/logout-all", status_code=204)
async def logout_all_sessions(
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[
        LogoutAllSessionsHandler, Depends(get_logout_all_sessions_handler)
    ],
) -> None:
    await handler.execute(LogoutAllSessionsCommand(employee_id=actor.employee_id.value))
