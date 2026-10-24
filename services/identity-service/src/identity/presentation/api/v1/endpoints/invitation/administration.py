from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.application.commands.invite_employee.command import InviteEmployeeCommand
from identity.application.commands.invite_employee.handler import InviteEmployeeHandler
from identity.application.commands.reissue_invitation.command import (
    ReissueInvitationCommand,
)
from identity.application.commands.reissue_invitation.handler import (
    ReissueInvitationHandler,
)
from identity.application.commands.revoke_invitation.command import (
    RevokeInvitationCommand,
)
from identity.application.commands.revoke_invitation.handler import (
    RevokeInvitationHandler,
)
from identity.presentation.api.dependencies.employee.authentication import get_actor
from identity.presentation.api.dependencies.invitation.administration import (
    get_invite_handler,
    get_reissue_handler,
    get_revoke_handler,
)
from identity.presentation.api.v1.schemas.invitation.administration import (
    InviteEmployeeRequest,
    InviteEmployeeResponse,
    ReissueInvitationRequest,
    ReissueInvitationResponse,
)

router = APIRouter(tags=["invitation administration"])


@router.post(
    "",
    response_model=InviteEmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_employee(
    body: InviteEmployeeRequest,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[InviteEmployeeHandler, Depends(get_invite_handler)],
) -> InviteEmployeeResponse:
    result = await handler.execute(
        InviteEmployeeCommand(
            inviter_id=actor.employee_id.value,
            employee_email=body.email,
            employee_roles=body.roles,
        )
    )
    return InviteEmployeeResponse.model_validate(result)


@router.post(
    "/reissue",
    response_model=ReissueInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reissue_invitation(
    body: ReissueInvitationRequest,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[ReissueInvitationHandler, Depends(get_reissue_handler)],
) -> ReissueInvitationResponse:
    result = await handler.execute(
        ReissueInvitationCommand(
            inviter_id=actor.employee_id.value,
            employee_email=body.email,
        )
    )
    return ReissueInvitationResponse.model_validate(result)


@router.delete(
    "/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invitation(
    invitation_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[RevokeInvitationHandler, Depends(get_revoke_handler)],
) -> None:
    await handler.execute(
        RevokeInvitationCommand(
            actor_id=actor.employee_id.value,
            invitation_id=invitation_id,
        )
    )
