from fastapi import APIRouter

from identity.presentation.api.dependencies.invitation.types import (
    InvitationDependencies,
)
from identity.presentation.api.v1.endpoints.invitation.acceptance import (
    create_invitation_acceptance_router,
)
from identity.presentation.api.v1.endpoints.invitation.administration import (
    create_invitation_administration_router,
)


def create_invitation_router(dependencies: InvitationDependencies) -> APIRouter:
    router = APIRouter()
    router.include_router(
        create_invitation_administration_router(dependencies), prefix="/invitations"
    )
    router.include_router(
        create_invitation_acceptance_router(dependencies), prefix="/invitations"
    )
    return router
