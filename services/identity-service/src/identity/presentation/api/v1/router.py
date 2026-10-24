from fastapi import APIRouter

from identity.presentation.api.dependencies.employee.types import EmployeeDependencies
from identity.presentation.api.dependencies.invitation.types import (
    InvitationDependencies,
)
from identity.presentation.api.v1.endpoints.employee.router import (
    create_employee_router,
)
from identity.presentation.api.v1.endpoints.invitation.router import (
    create_invitation_router,
)


def create_v1_router(
    employee_dependencies: EmployeeDependencies,
    invitation_dependencies: InvitationDependencies,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(create_employee_router(employee_dependencies))
    router.include_router(create_invitation_router(invitation_dependencies))
    return router
