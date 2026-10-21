from typing import Annotated

from fastapi import APIRouter, Depends, status

from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.application.commands.change_email.command import ChangeEmailCommand
from identity.application.commands.change_email.handler import ChangeEmailHandler
from identity.application.commands.change_password.command import ChangePasswordCommand
from identity.application.commands.change_password.handler import ChangePasswordHandler
from identity.application.queries.get_current_employee.handler import (
    GetCurrentEmployeeHandler,
)
from identity.application.queries.get_current_employee.query import (
    GetCurrentEmployeeQuery,
)
from identity.presentation.api.dependencies.employee.types import EmployeeDependencies
from identity.presentation.api.v1.schemas.employee import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    EmployeeResponse,
)


def create_profile_router(dependencies: EmployeeDependencies) -> APIRouter:
    router = APIRouter(prefix="/employees/me", tags=["employee profile"])

    @router.get("", response_model=EmployeeResponse)
    async def get_current_employee(
        actor: Annotated[CurrentActor, Depends(dependencies.actor)],
        handler: Annotated[
            GetCurrentEmployeeHandler, Depends(dependencies.current_employee)
        ],
    ) -> EmployeeResponse:
        result = await handler.execute(
            GetCurrentEmployeeQuery(employee_id=actor.employee_id.value)
        )
        return EmployeeResponse.model_validate(result)

    @router.patch("/email", status_code=status.HTTP_204_NO_CONTENT)
    async def change_email(
        body: ChangeEmailRequest,
        actor: Annotated[CurrentActor, Depends(dependencies.actor)],
        handler: Annotated[ChangeEmailHandler, Depends(dependencies.change_email)],
    ) -> None:
        await handler.execute(
            ChangeEmailCommand(
                employee_id=actor.employee_id.value,
                new_email=body.new_email,
                password=body.password.get_secret_value(),
            )
        )

    @router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
    async def change_password(
        body: ChangePasswordRequest,
        actor: Annotated[CurrentActor, Depends(dependencies.actor)],
        handler: Annotated[
            ChangePasswordHandler, Depends(dependencies.change_password)
        ],
    ) -> None:
        await handler.execute(
            ChangePasswordCommand(
                employee_id=actor.employee_id.value,
                current_password=body.current_password.get_secret_value(),
                new_password=body.new_password.get_secret_value(),
            )
        )

    return router
