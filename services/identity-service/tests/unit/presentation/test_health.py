import asyncio

from sqlalchemy.exc import OperationalError

from identity.domain.enums.role import EmployeeRole
from identity.presentation.api import health
from tests.unit.presentation.api.v1.support import FakeSession, make_app, request


class UnavailableSession(FakeSession):
    async def execute(self, statement, params=None):
        raise OperationalError("SELECT 1", {}, OSError("connection refused"))


class HangingSession(FakeSession):
    async def execute(self, statement, params=None):
        await asyncio.sleep(10)


def test_liveness_does_not_touch_database() -> None:
    session = FakeSession([EmployeeRole.ADMIN])

    status_code, body = request(make_app(session), "GET", "/health/live")

    assert status_code == 200
    assert body == {"status": "ok"}
    assert session.entries == 0


def test_readiness_reports_ok_when_database_responds() -> None:
    session = FakeSession([EmployeeRole.ADMIN])

    status_code, body = request(make_app(session), "GET", "/health/ready")

    assert status_code == 200
    assert body == {"status": "ok"}
    assert session.entries == 1


def test_readiness_reports_unavailable_without_leaking_error() -> None:
    session = UnavailableSession([EmployeeRole.ADMIN])

    status_code, body = request(make_app(session), "GET", "/health/ready")

    assert status_code == 503
    assert body == {"status": "unavailable"}


def test_readiness_times_out_when_database_hangs(monkeypatch) -> None:
    monkeypatch.setattr(health, "DATABASE_CHECK_TIMEOUT_SECONDS", 0.01)
    session = HangingSession([EmployeeRole.ADMIN])

    status_code, body = request(make_app(session), "GET", "/health/ready")

    assert status_code == 503
    assert body == {"status": "unavailable"}


def test_health_routes_are_not_versioned() -> None:
    paths = make_app(FakeSession([EmployeeRole.ADMIN])).openapi()["paths"]

    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/api/v1/health/ready" not in paths
