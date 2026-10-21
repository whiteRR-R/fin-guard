from fastapi import APIRouter

from identity.presentation.api.dependencies.employee.types import EmployeeDependencies
from identity.presentation.api.v1.endpoints.employee.administration import (
    create_administration_router,
)
from identity.presentation.api.v1.endpoints.employee.auth import create_auth_router
from identity.presentation.api.v1.endpoints.employee.profile import (
    create_profile_router,
)


def create_employee_router(dependencies: EmployeeDependencies) -> APIRouter:
    router = APIRouter()
    router.include_router(create_auth_router(dependencies))
    router.include_router(create_profile_router(dependencies))
    router.include_router(create_administration_router(dependencies))
    return router
