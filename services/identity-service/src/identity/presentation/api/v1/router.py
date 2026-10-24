from fastapi import APIRouter

from identity.presentation.api.v1.endpoints.employee.router import (
    router as employee_router,
)
from identity.presentation.api.v1.endpoints.invitation.router import (
    router as invitation_router,
)

router = APIRouter(prefix="/api/v1")
router.include_router(employee_router)
router.include_router(invitation_router)
