from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.application.commands.revoke_own_session.command import (
    RevokeOwnSessionCommand,
)
from identity.application.commands.revoke_own_session.handler import (
    RevokeOwnSessionHandler,
)
from identity.application.queries.list_own_sessions.handler import (
    ListOwnSessionsHandler,
)
from identity.application.queries.list_own_sessions.query import ListOwnSessionsQuery
from identity.presentation.api.dependencies.employee.authentication import get_actor
from identity.presentation.api.dependencies.employee.sessions import (
    get_list_own_sessions_handler,
    get_revoke_own_session_handler,
)
from identity.presentation.api.v1.schemas.session import OwnSessionsResponse

router = APIRouter(prefix="/employees/me/sessions", tags=["employee sessions"])


@router.get("", response_model=OwnSessionsResponse)
async def list_own_sessions(
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[ListOwnSessionsHandler, Depends(get_list_own_sessions_handler)],
) -> OwnSessionsResponse:
    result = await handler.execute(
        ListOwnSessionsQuery(
            employee_id=actor.employee_id.value,
            current_session_id=actor.session_id.value,
        )
    )
    return OwnSessionsResponse.model_validate(result, from_attributes=True)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_own_session(
    session_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[
        RevokeOwnSessionHandler, Depends(get_revoke_own_session_handler)
    ],
) -> None:
    await handler.execute(
        RevokeOwnSessionCommand(
            employee_id=actor.employee_id.value,
            target_session_id=session_id,
        )
    )
