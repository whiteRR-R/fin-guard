from fastapi import APIRouter

from identity.presentation.api.v1.endpoints.invitation.acceptance import (
    router as acceptance_router,
)
from identity.presentation.api.v1.endpoints.invitation.administration import (
    router as administration_router,
)

router = APIRouter()
router.include_router(administration_router, prefix="/invitations")
router.include_router(acceptance_router, prefix="/invitations")
