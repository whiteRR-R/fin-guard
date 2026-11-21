import asyncio
import re

from httpx import ASGITransport, AsyncClient

from identity.domain.enums.role import EmployeeRole
from tests.unit.presentation.api.v1.support import FakeSession, make_app

TOKEN = "c_H8CDI8RkW-thteiXX2cNWDRRZkTOKEN"


def get_page(path: str = f"/invitations/accept?token={TOKEN}"):
    app = make_app(FakeSession([EmployeeRole.ADMIN]))

    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(path)

    return asyncio.run(send())


def test_page_is_served_as_html_form() -> None:
    response = get_page()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="password"' in response.text
    assert 'id="confirmation"' in response.text
    assert '"/api/v1/invitations/accept"' in response.text


def test_token_is_never_reflected_into_html() -> None:
    response = get_page(
        "/invitations/accept?token=%3Cscript%3Ealert(1)%3C%2Fscript%3E" + TOKEN
    )

    assert TOKEN not in response.text
    assert "alert(1)" not in response.text


def test_page_uses_per_request_nonce_in_strict_csp() -> None:
    first = get_page()
    second = get_page()

    policy = first.headers["content-security-policy"]
    nonce = re.search(r"script-src 'nonce-([^']+)'", policy).group(1)
    assert f'<script nonce="{nonce}">' in first.text
    assert f'<style nonce="{nonce}">' in first.text
    assert "unsafe-inline" not in policy
    assert "default-src 'none'" in policy
    assert "connect-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert nonce not in second.headers["content-security-policy"]


def test_page_is_not_cached_and_does_not_leak_referrer() -> None:
    headers = get_page().headers

    assert headers["cache-control"] == "no-store"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"


def test_script_removes_token_from_address_bar() -> None:
    assert "history.replaceState" in get_page().text


def test_page_is_also_served_at_legacy_path() -> None:
    response = get_page(f"/accept-invitation?token={TOKEN}")

    assert response.status_code == 200
    assert 'id="password"' in response.text
    assert TOKEN not in response.text


def test_page_is_not_part_of_api_schema() -> None:
    paths = make_app(FakeSession([EmployeeRole.ADMIN])).openapi()["paths"]

    assert "/invitations/accept" not in paths
    assert "/accept-invitation" not in paths
