from typing import Annotated

from fastapi import APIRouter, Depends, status

from identity.application.commands.accept_invitation.command import (
    AcceptInvitationCommand,
)
from identity.application.commands.accept_invitation.handler import (
    AcceptInvitationHandler,
)
from identity.presentation.api.dependencies.invitation.types import (
    InvitationDependencies,
)
from identity.presentation.api.v1.schemas.invitation.acceptance import (
    AcceptInvitationRequest,
)


def create_invitation_acceptance_router(
    dependencies: InvitationDependencies,
) -> APIRouter:
    router = APIRouter(tags=["invitation acceptance"])

    @router.post("/accept", status_code=status.HTTP_204_NO_CONTENT)
    async def accept_invitation(
        body: AcceptInvitationRequest,
        handler: Annotated[AcceptInvitationHandler, Depends(dependencies.accept)],
    ) -> None:
        await handler.execute(
            AcceptInvitationCommand(
                token=body.token.get_secret_value(),
                password=body.password.get_secret_value(),
            )
        )

    return router
