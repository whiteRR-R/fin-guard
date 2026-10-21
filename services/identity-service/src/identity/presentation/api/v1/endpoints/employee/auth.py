from typing import Annotated

from fastapi import APIRouter, Depends

from identity.application.commands.login_employee.command import LoginEmployeeCommand
from identity.application.commands.login_employee.handler import LoginEmployeeHandler
from identity.presentation.api.dependencies.employee.types import EmployeeDependencies
from identity.presentation.api.v1.schemas.employee import LoginRequest, LoginResponse


def create_auth_router(dependencies: EmployeeDependencies) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["employee authentication"])

    @router.post("/login", response_model=LoginResponse)
    async def login(
        body: LoginRequest,
        handler: Annotated[LoginEmployeeHandler, Depends(dependencies.login)],
    ) -> LoginResponse:
        result = await handler.execute(
            LoginEmployeeCommand(
                email=body.email,
                password=body.password.get_secret_value(),
            )
        )
        return LoginResponse.model_validate(result, from_attributes=True)

    return router
