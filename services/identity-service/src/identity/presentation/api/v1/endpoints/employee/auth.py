from typing import Annotated

from fastapi import APIRouter, Depends

from identity.application.commands.login_employee.command import LoginEmployeeCommand
from identity.application.commands.login_employee.handler import LoginEmployeeHandler
from identity.presentation.api.dependencies.employee.authentication import (
    get_login_handler,
)
from identity.presentation.api.v1.schemas.employee import LoginRequest, LoginResponse

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
