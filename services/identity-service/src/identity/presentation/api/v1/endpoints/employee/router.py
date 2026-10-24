from fastapi import APIRouter

from identity.presentation.api.v1.endpoints.employee.administration import (
    router as administration_router,
)
from identity.presentation.api.v1.endpoints.employee.auth import router as auth_router
from identity.presentation.api.v1.endpoints.employee.profile import (
    router as profile_router,
)
from identity.presentation.api.v1.endpoints.employee.sessions import (
    router as sessions_router,
)

router = APIRouter()
router.include_router(auth_router)
router.include_router(profile_router)
router.include_router(sessions_router)
router.include_router(administration_router)
