from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.application.commands.create_service_account.command import (
    CreateServiceAccountCommand,
)
from identity.application.commands.create_service_account.handler import (
    CreateServiceAccountHandler,
)
from identity.application.commands.revoke_service_account.command import (
    RevokeServiceAccountCommand,
)
from identity.application.commands.revoke_service_account.handler import (
    RevokeServiceAccountHandler,
)
from identity.application.commands.rotate_client_secret.command import (
    RotateClientSecretCommand,
)
from identity.application.commands.rotate_client_secret.handler import (
    RotateClientSecretHandler,
)
from identity.application.queries.get_service_account.handler import (
    GetServiceAccountHandler,
)
from identity.application.queries.get_service_account.query import (
    GetServiceAccountQuery,
)
from identity.application.queries.list_service_accounts.handler import (
    ListServiceAccountsHandler,
)
from identity.application.queries.list_service_accounts.query import (
    ListServiceAccountsQuery,
)
from identity.presentation.api.dependencies.employee.authentication import get_actor
from identity.presentation.api.dependencies.service_account.administration import (
    get_create_service_account_handler,
    get_list_service_accounts_handler,
    get_revoke_service_account_handler,
    get_rotate_client_secret_handler,
    get_service_account_handler,
)
from identity.presentation.api.v1.schemas.service_account import (
    CreatedServiceAccountResponse,
    CreateServiceAccountRequest,
    RotatedClientSecretResponse,
    ServiceAccountPageResponse,
    ServiceAccountResponse,
)

router = APIRouter(prefix="/service-accounts", tags=["service accounts"])


def _do_not_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post(
    "",
    response_model=CreatedServiceAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_account(
    body: CreateServiceAccountRequest,
    response: Response,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[
        CreateServiceAccountHandler, Depends(get_create_service_account_handler)
    ],
) -> CreatedServiceAccountResponse:
    result = await handler.execute(
        CreateServiceAccountCommand(
            actor_id=actor.employee_id.value,
            name=body.name,
            scopes=body.scopes,
        )
    )
    _do_not_cache(response)
    return CreatedServiceAccountResponse.model_validate(result)


@router.get("", response_model=ServiceAccountPageResponse)
async def list_service_accounts(
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[
        ListServiceAccountsHandler, Depends(get_list_service_accounts_handler)
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ServiceAccountPageResponse:
    result = await handler.execute(
        ListServiceAccountsQuery(
            actor_id=actor.employee_id.value,
            limit=limit,
            offset=offset,
        )
    )
    return ServiceAccountPageResponse.model_validate(result)


@router.get("/{service_account_id}", response_model=ServiceAccountResponse)
async def get_service_account(
    service_account_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[GetServiceAccountHandler, Depends(get_service_account_handler)],
) -> ServiceAccountResponse:
    result = await handler.execute(
        GetServiceAccountQuery(
            actor_id=actor.employee_id.value,
            service_account_id=service_account_id,
        )
    )
    return ServiceAccountResponse.model_validate(result)


@router.post(
    "/{service_account_id}/secrets",
    response_model=RotatedClientSecretResponse,
    status_code=status.HTTP_201_CREATED,
)
async def rotate_client_secret(
    service_account_id: UUID,
    response: Response,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[
        RotateClientSecretHandler, Depends(get_rotate_client_secret_handler)
    ],
) -> RotatedClientSecretResponse:
    result = await handler.execute(
        RotateClientSecretCommand(
            actor_id=actor.employee_id.value,
            service_account_id=service_account_id,
        )
    )
    _do_not_cache(response)
    return RotatedClientSecretResponse.model_validate(result)


@router.delete(
    "/{service_account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_service_account(
    service_account_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_actor)],
    handler: Annotated[
        RevokeServiceAccountHandler, Depends(get_revoke_service_account_handler)
    ],
) -> None:
    await handler.execute(
        RevokeServiceAccountCommand(
            actor_id=actor.employee_id.value,
            service_account_id=service_account_id,
        )
    )
