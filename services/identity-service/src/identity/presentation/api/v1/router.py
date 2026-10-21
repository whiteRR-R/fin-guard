from fastapi import APIRouter

from identity.presentation.api.dependencies.employee.types import EmployeeDependencies
from identity.presentation.api.v1.endpoints.employee.router import (
    create_employee_router,
)


def create_v1_router(employee_dependencies: EmployeeDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(create_employee_router(employee_dependencies))
    return router
