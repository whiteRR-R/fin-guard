from fastapi import APIRouter

from identity.presentation.api.v1.endpoints.service_account.administration import (
    router as administration_router,
)
from identity.presentation.api.v1.endpoints.service_account.token import (
    router as token_router,
)

router = APIRouter()
router.include_router(administration_router)
router.include_router(token_router)
