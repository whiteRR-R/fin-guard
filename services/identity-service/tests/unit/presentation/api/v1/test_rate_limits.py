from datetime import timedelta
from urllib.parse import urlencode

from identity.domain.enums.role import EmployeeRole
from identity.infrastructure.rate_limit.limits import RateLimit
from identity.presentation.api.rate_limit import AuthenticationRateLimits
from tests.unit.presentation.api.v1.support import (
    FakeSession,
    InMemoryRateLimiter,
    make_app,
    request,
)

STRICT = AuthenticationRateLimits(
    login_per_ip=RateLimit("login:ip", 5, timedelta(minutes=5)),
    login_failures_per_email=RateLimit("login:email", 2, timedelta(minutes=15)),
    token_per_ip=RateLimit("token:ip", 5, timedelta(minutes=1)),
    token_failures_per_client=RateLimit("token:client", 2, timedelta(minutes=5)),
)
CLIENT_ID = "sa_" + "a" * 32


def login(app, password: str, email: str = "employee@example.com"):
    return request(
        app,
        "POST",
        "/api/v1/auth/login",
        body={"email": email, "password": password},
    )


def strict_app():
    limiter = InMemoryRateLimiter()
    app = make_app(
        FakeSession([EmployeeRole.ADMIN]), rate_limiter=limiter, rate_limits=STRICT
    )
    return app, limiter


def test_repeated_login_failures_for_email_are_blocked() -> None:
    app, limiter = strict_app()

    assert login(app, "wrong-password-1")[0] == 401
    assert login(app, "wrong-password-2")[0] == 401
    status, body = login(app, "valid-password-long")

    assert status == 429
    assert body == {"detail": "Too many attempts, try again later"}
    assert limiter.count("login:email", "employee@example.com") == 2


def test_email_limit_ignores_case_and_whitespace() -> None:
    app, limiter = strict_app()

    login(app, "wrong-password-1", email="Employee@Example.com")
    login(app, "wrong-password-2", email="EMPLOYEE@example.com")

    assert limiter.count("login:email", "employee@example.com") == 2
    assert login(app, "valid-password-long")[0] == 429


def test_successful_logins_do_not_count_against_email() -> None:
    app, limiter = strict_app()

    for _ in range(3):
        assert login(app, "valid-password-long")[0] == 200

    assert limiter.count("login:email", "employee@example.com") == 0


def test_login_attempts_per_ip_are_limited() -> None:
    app, limiter = strict_app()

    statuses = [login(app, "valid-password-long")[0] for _ in range(6)]

    assert statuses == [200] * 5 + [429]
    assert limiter.count("login:ip", "127.0.0.1") == 5


def test_rate_limited_login_returns_retry_after() -> None:
    import asyncio

    from httpx import ASGITransport, AsyncClient

    app, _ = strict_app()
    login(app, "wrong-password-1")
    login(app, "wrong-password-2")

    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/api/v1/auth/login",
                json={"email": "employee@example.com", "password": "x" * 12},
            )

    response = asyncio.run(send())

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def token(app, client_secret: str):
    import asyncio

    from httpx import ASGITransport, AsyncClient

    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/api/v1/oauth/token",
                content=urlencode(
                    {
                        "grant_type": "client_credentials",
                        "client_id": CLIENT_ID,
                        "client_secret": client_secret,
                    }
                ),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

    return asyncio.run(send())


def test_token_failures_per_client_are_blocked() -> None:
    app, limiter = strict_app()

    assert token(app, "wrong-1").status_code == 401
    assert token(app, "wrong-2").status_code == 401
    blocked = token(app, "wrong-3")

    assert blocked.status_code == 429
    assert blocked.json() == {"error": "too_many_requests"}
    assert int(blocked.headers["retry-after"]) > 0
    assert blocked.headers["cache-control"] == "no-store"
    assert limiter.count("token:client", CLIENT_ID) == 2


def test_token_requests_per_ip_are_limited() -> None:
    app, limiter = strict_app()

    statuses = [token(app, "wrong").status_code for _ in range(6)]

    assert statuses[-1] == 429
    assert limiter.count("token:ip", "127.0.0.1") == 5
