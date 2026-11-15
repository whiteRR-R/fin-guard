from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Protocol, cast

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from identity.infrastructure.config import RateLimitSettings
from identity.infrastructure.rate_limit.limits import RateLimit, RateLimitExceededError


class RateLimiter(Protocol):
    async def ensure_allowed(self, *checks: tuple[RateLimit, str]) -> None: ...

    async def record(self, *hits: tuple[RateLimit, str]) -> None: ...


@dataclass(frozen=True, slots=True)
class AuthenticationRateLimits:
    login_per_ip: RateLimit
    login_failures_per_email: RateLimit
    token_per_ip: RateLimit
    token_failures_per_client: RateLimit

    @classmethod
    def from_settings(cls, settings: RateLimitSettings) -> "AuthenticationRateLimits":
        return cls(
            login_per_ip=RateLimit(
                "login:ip",
                settings.login_attempts_per_ip,
                timedelta(seconds=settings.login_ip_window_seconds),
            ),
            login_failures_per_email=RateLimit(
                "login:email",
                settings.login_failures_per_email,
                timedelta(seconds=settings.login_email_window_seconds),
            ),
            token_per_ip=RateLimit(
                "token:ip",
                settings.token_requests_per_ip,
                timedelta(seconds=settings.token_ip_window_seconds),
            ),
            token_failures_per_client=RateLimit(
                "token:client",
                settings.token_failures_per_client,
                timedelta(seconds=settings.token_client_window_seconds),
            ),
        )


@dataclass(frozen=True, slots=True)
class RateLimitGuard:
    limiter: RateLimiter
    limits: AuthenticationRateLimits


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _guard(request: Request) -> RateLimitGuard:
    return cast(RateLimitGuard, request.app.state.identity_rate_limit)


async def get_rate_limit_guard(request: Request) -> RateLimitGuard:
    return _guard(request)


RateLimitGuardDependency = Annotated[RateLimitGuard, Depends(get_rate_limit_guard)]


def too_many_requests(retry_after: int, content: dict[str, str]) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=content,
        headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
    )


def install_rate_limit_handler(app: FastAPI) -> None:
    @app.exception_handler(RateLimitExceededError)
    async def rate_limited(
        request: Request, error: RateLimitExceededError
    ) -> JSONResponse:
        return too_many_requests(
            error.retry_after, {"detail": "Too many attempts, try again later"}
        )
