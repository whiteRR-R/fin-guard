from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.application.commands.assign_role.command import AssignRoleCommand
from identity.application.commands.assign_role.handler import AssignRoleHandler
from identity.application.commands.block_employee.command import BlockEmployeeCommand
from identity.application.commands.block_employee.handler import BlockEmployeeHandler
from identity.application.commands.revoke_role.command import RevokeRoleCommand
from identity.application.commands.revoke_role.handler import RevokeRoleHandler
from identity.application.commands.unblock_employee.command import (
    UnblockEmployeeCommand,
)
from identity.application.commands.unblock_employee.handler import (
    UnblockEmployeeHandler,
)
from identity.application.queries.get_employee.handler import GetEmployeeHandler
from identity.application.queries.get_employee.query import GetEmployeeQuery
from identity.application.queries.list_employees.handler import ListEmployeesHandler
from identity.application.queries.list_employees.query import ListEmployeesQuery
from identity.domain.enums.role import EmployeeRole
from identity.presentation.api.dependencies.employee.administration import (
    get_assign_role_handler,
    get_block_employee_handler,
    get_employee_handler,
    get_list_employees_handler,
    get_revoke_role_handler,
    get_unblock_employee_handler,
)
from identity.presentation.api.dependencies.employee.authentication import get_actor
from identity.presentation.api.v1.schemas.employee import (
    EmployeePageResponse,
    EmployeeResponse,
    EmployeeStatusResponse,
)

router = APIRouter(prefix="/employees", tags=["employee administration"])


@router.get("", response_model=EmployeePageResponse)
async def list_employees(
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[ListEmployeesHandler, Depends(get_list_employees_handler)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EmployeePageResponse:
    result = await handler.execute(
        ListEmployeesQuery(
            actor_id=actor.employee_id.value,
            limit=limit,
            offset=offset,
        )
    )
    return EmployeePageResponse(
        employees=tuple(
            EmployeeResponse.model_validate(item) for item in result.employees
        ),
        limit=result.limit,
        offset=result.offset,
        has_more=result.has_more,
    )


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[GetEmployeeHandler, Depends(get_employee_handler)],
) -> EmployeeResponse:
    result = await handler.execute(
        GetEmployeeQuery(
            actor_id=actor.employee_id.value,
            employee_id=employee_id,
        )
    )
    return EmployeeResponse.model_validate(result)


@router.post("/{employee_id}/block", response_model=EmployeeStatusResponse)
async def block_employee(
    employee_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[BlockEmployeeHandler, Depends(get_block_employee_handler)],
) -> EmployeeStatusResponse:
    result = await handler.execute(
        BlockEmployeeCommand(
            target_id=employee_id,
            actor_id=actor.employee_id.value,
        )
    )
    return EmployeeStatusResponse.model_validate(result)


@router.post("/{employee_id}/unblock", response_model=EmployeeStatusResponse)
async def unblock_employee(
    employee_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[UnblockEmployeeHandler, Depends(get_unblock_employee_handler)],
) -> EmployeeStatusResponse:
    result = await handler.execute(
        UnblockEmployeeCommand(
            target_id=employee_id,
            actor_id=actor.employee_id.value,
        )
    )
    return EmployeeStatusResponse.model_validate(result)


@router.put(
    "/{employee_id}/roles/{role}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def assign_role(
    employee_id: UUID,
    role: EmployeeRole,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[AssignRoleHandler, Depends(get_assign_role_handler)],
) -> None:
    await handler.execute(
        AssignRoleCommand(
            actor_id=actor.employee_id.value,
            employee_id=employee_id,
            role=role,
        )
    )


@router.delete(
    "/{employee_id}/roles/{role}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_role(
    employee_id: UUID,
    role: EmployeeRole,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[RevokeRoleHandler, Depends(get_revoke_role_handler)],
) -> None:
    await handler.execute(
        RevokeRoleCommand(
            actor_id=actor.employee_id.value,
            employee_id=employee_id,
            role=role,
        )
    )
