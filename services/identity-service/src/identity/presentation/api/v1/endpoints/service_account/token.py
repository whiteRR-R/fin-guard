import base64
import binascii
from typing import Annotated
from urllib.parse import parse_qsl, unquote_plus

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from identity.application.commands.issue_machine_access_token.command import (
    IssueMachineAccessTokenCommand,
)
from identity.application.commands.issue_machine_access_token.handler import (
    IssueMachineAccessTokenHandler,
)
from identity.application.exceptions import InvalidClientError, InvalidScopeError
from identity.infrastructure.rate_limit.limits import RateLimitExceededError
from identity.presentation.api.dependencies.service_account.token import (
    get_issue_machine_access_token_handler,
)
from identity.presentation.api.dependencies.services import ClockDependency
from identity.presentation.api.rate_limit import (
    RateLimitGuardDependency,
    client_ip,
    too_many_requests,
)
from identity.presentation.api.v1.schemas.service_account import (
    MachineAccessTokenResponse,
    OAuthErrorResponse,
)

router = APIRouter(prefix="/oauth", tags=["oauth"])

MAX_BODY_BYTES = 4096
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class OAuthError(Exception):
    def __init__(self, error: str, status_code: int = 400) -> None:
        super().__init__(error)
        self.error = error
        self.status_code = status_code


def _error_response(error: OAuthError) -> JSONResponse:
    headers = dict(NO_STORE_HEADERS)
    if error.status_code == 401:
        headers["WWW-Authenticate"] = 'Basic realm="identity"'
    return JSONResponse(
        status_code=error.status_code,
        content={"error": error.error},
        headers=headers,
    )


async def _read_form(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if content_type.split(";", 1)[0].strip().lower() != FORM_CONTENT_TYPE:
        raise OAuthError("invalid_request")

    declared_length = request.headers.get("content-length")
    if declared_length is not None and (
        not declared_length.isdigit() or int(declared_length) > MAX_BODY_BYTES
    ):
        raise OAuthError("invalid_request")

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise OAuthError("invalid_request")

    try:
        pairs = parse_qsl(body.decode("utf-8"), keep_blank_values=True)
    except (UnicodeDecodeError, ValueError) as error:
        raise OAuthError("invalid_request") from error

    form: dict[str, str] = {}
    for key, value in pairs:
        if key in form:
            raise OAuthError("invalid_request")
        form[key] = value
    return form


def _basic_credentials(request: Request) -> tuple[str, str] | None:
    authorization = request.headers.get("authorization")
    if authorization is None:
        return None

    scheme, _, encoded = authorization.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        raise OAuthError("invalid_client", status_code=401)

    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise OAuthError("invalid_client", status_code=401) from error

    client_id, separator, client_secret = decoded.partition(":")
    if not separator:
        raise OAuthError("invalid_client", status_code=401)
    return unquote_plus(client_id), unquote_plus(client_secret)


def _client_credentials(request: Request, form: dict[str, str]) -> tuple[str, str]:
    basic = _basic_credentials(request)
    in_body = "client_id" in form or "client_secret" in form

    if basic is not None and in_body:
        raise OAuthError("invalid_request")

    if basic is not None:
        return basic

    client_id = form.get("client_id", "")
    client_secret = form.get("client_secret", "")
    if not client_id or not client_secret:
        raise OAuthError("invalid_client", status_code=401)
    return client_id, client_secret


def _requested_scopes(form: dict[str, str]) -> tuple[str, ...] | None:
    scopes = tuple(form.get("scope", "").split())
    return scopes or None


@router.post(
    "/token",
    response_model=MachineAccessTokenResponse,
    responses={
        400: {"model": OAuthErrorResponse},
        401: {"model": OAuthErrorResponse},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                FORM_CONTENT_TYPE: {
                    "schema": {
                        "type": "object",
                        "required": ["grant_type"],
                        "properties": {
                            "grant_type": {
                                "type": "string",
                                "enum": ["client_credentials"],
                            },
                            "client_id": {"type": "string"},
                            "client_secret": {"type": "string", "format": "password"},
                            "scope": {"type": "string"},
                        },
                    }
                }
            },
        }
    },
)
async def issue_machine_access_token(
    request: Request,
    clock: ClockDependency,
    guard: RateLimitGuardDependency,
    handler: Annotated[
        IssueMachineAccessTokenHandler,
        Depends(get_issue_machine_access_token_handler),
    ],
) -> JSONResponse:
    ip_check = (guard.limits.token_per_ip, client_ip(request))
    try:
        await guard.limiter.ensure_allowed(ip_check)
        await guard.limiter.record(ip_check)
    except RateLimitExceededError as error:
        return too_many_requests(error.retry_after, {"error": "too_many_requests"})

    try:
        form = await _read_form(request)

        grant_type = form.get("grant_type")
        if not grant_type:
            raise OAuthError("invalid_request")
        if grant_type != "client_credentials":
            raise OAuthError("unsupported_grant_type")

        client_id, client_secret = _client_credentials(request, form)
        client_check = (guard.limits.token_failures_per_client, client_id)

        try:
            await guard.limiter.ensure_allowed(client_check)
        except RateLimitExceededError as error:
            return too_many_requests(error.retry_after, {"error": "too_many_requests"})

        try:
            result = await handler.execute(
                IssueMachineAccessTokenCommand(
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=_requested_scopes(form),
                )
            )
        except InvalidClientError as error:
            await guard.limiter.record(client_check)
            raise OAuthError("invalid_client", status_code=401) from error
        except InvalidScopeError as error:
            raise OAuthError("invalid_scope") from error
    except OAuthError as error:
        return _error_response(error)

    expires_in = max(0, int((result.expires_at - clock.now()).total_seconds()))
    body = MachineAccessTokenResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_in=expires_in,
        scope=" ".join(scope.value for scope in result.scopes),
    )
    return JSONResponse(content=body.model_dump(), headers=NO_STORE_HEADERS)
