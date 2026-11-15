import asyncio
import base64
from datetime import timedelta
from urllib.parse import quote, urlencode

import pytest
from httpx import ASGITransport, AsyncClient

from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.application.commands.create_service_account.handler import (
    CreateServiceAccountHandler,
)
from identity.application.commands.issue_machine_access_token.handler import (
    IssueMachineAccessTokenHandler,
)
from identity.application.commands.revoke_service_account.handler import (
    RevokeServiceAccountHandler,
)
from identity.application.commands.rotate_client_secret.handler import (
    RotateClientSecretHandler,
)
from identity.application.queries.get_service_account.handler import (
    GetServiceAccountHandler,
)
from identity.application.queries.list_service_accounts.handler import (
    ListServiceAccountsHandler,
)
from identity.domain.enums.role import EmployeeRole
from identity.domain.value_objects.refresh_session import RefreshSessionId
from identity.presentation.api.dependencies.employee.authentication import get_actor
from identity.presentation.api.dependencies.service_account.administration import (
    get_create_service_account_handler,
    get_list_service_accounts_handler,
    get_revoke_service_account_handler,
    get_rotate_client_secret_handler,
    get_service_account_handler,
)
from identity.presentation.api.dependencies.service_account.token import (
    get_issue_machine_access_token_handler,
)
from identity.presentation.api.dependencies.services import get_clock
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    FixedClock,
    OutboxRepositoryFake,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee
from tests.unit.application.service_account_support import (
    CLIENT_ID,
    GRACE,
    NOW,
    PLAIN_SECRET,
    ClientCredentialsStub,
    MachineTokenIssuerStub,
    ServiceAccountRepositoryFake,
    make_service_account,
)
from tests.unit.presentation.api.v1.support import FakeSession, make_app

FORM = "application/x-www-form-urlencoded"


class Api:
    def __init__(
        self,
        *,
        roles=(EmployeeRole.ADMIN,),
        authenticated: bool = True,
        accounts=(),
    ) -> None:
        self.actor = make_employee("admin@example.com", roles=roles)
        self.employees = EmployeeRepositoryFake((self.actor,))
        self.accounts = ServiceAccountRepositoryFake(accounts)
        self.outbox = OutboxRepositoryFake()
        self.clock = FixedClock(NOW)
        self.credentials = ClientCredentialsStub()
        self.tokens = MachineTokenIssuerStub()
        self.app = make_app(FakeSession([EmployeeRole.ADMIN]))

        overrides = self.app.dependency_overrides
        if authenticated:
            overrides[get_actor] = lambda: CurrentActor(
                employee_id=self.actor.id,
                session_id=RefreshSessionId.new(),
                roles=self.actor.roles,
            )
        overrides[get_clock] = lambda: self.clock
        common = {
            "clock": self.clock,
            "employees": self.employees,
            "service_accounts": self.accounts,
        }
        overrides[get_create_service_account_handler] = lambda: (
            CreateServiceAccountHandler(
                uow=UnitOfWorkFake(),
                outbox=self.outbox,
                credentials=self.credentials,
                **common,
            )
        )
        overrides[get_rotate_client_secret_handler] = lambda: RotateClientSecretHandler(
            uow=UnitOfWorkFake(),
            outbox=self.outbox,
            credentials=self.credentials,
            grace_period=GRACE,
            **common,
        )
        overrides[get_revoke_service_account_handler] = lambda: (
            RevokeServiceAccountHandler(
                uow=UnitOfWorkFake(), outbox=self.outbox, **common
            )
        )
        overrides[get_service_account_handler] = lambda: GetServiceAccountHandler(
            uow=UnitOfWorkFake(), **common
        )
        overrides[get_list_service_accounts_handler] = lambda: (
            ListServiceAccountsHandler(uow=UnitOfWorkFake(), **common)
        )
        overrides[get_issue_machine_access_token_handler] = lambda: (
            IssueMachineAccessTokenHandler(
                uow=UnitOfWorkFake(),
                clock=self.clock,
                service_accounts=self.accounts,
                secret_verifier=self.credentials,
                token_issuer=self.tokens,
            )
        )

    def request(self, method: str, path: str, **kwargs):
        async def send():
            async with AsyncClient(
                transport=ASGITransport(app=self.app), base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def token(self, form: dict[str, str] | str, **kwargs):
        content = form if isinstance(form, str) else urlencode(form)
        headers = {"Content-Type": FORM, **kwargs.pop("headers", {})}
        return self.request(
            "POST", "/api/v1/oauth/token", content=content, headers=headers, **kwargs
        )


def basic(client_id: str, client_secret: str) -> str:
    raw = f"{quote(client_id, safe='')}:{quote(client_secret, safe='')}"
    return "Basic " + base64.b64encode(raw.encode()).decode()


def credentials_form(**extra: str) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": PLAIN_SECRET,
        **extra,
    }


# ---------- administration ----------


def test_admin_creates_service_account_and_gets_secret_once() -> None:
    api = Api()

    response = api.request(
        "POST",
        "/api/v1/service-accounts",
        json={"name": "Bank X", "scopes": ["transactions:write", "transactions:read"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["client_secret"] == "plain-secret-new"
    assert body["client_id"] == "sa_" + "n" * 32
    assert body["scopes"] == ["transactions:read", "transactions:write"]
    assert response.headers["cache-control"] == "no-store"
    assert len(api.accounts.added) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Bank", "scopes": []},
        {"name": "Bank", "scopes": ["ADMIN"]},
        {"name": "", "scopes": ["transactions:read"]},
        {"name": "Bank", "scopes": ["transactions:read"], "roles": ["ADMIN"]},
    ],
)
def test_create_rejects_invalid_payload(payload) -> None:
    api = Api()

    response = api.request("POST", "/api/v1/service-accounts", json=payload)

    assert response.status_code == 422
    assert api.accounts.added == []


def test_create_requires_admin() -> None:
    api = Api(roles=(EmployeeRole.RISK_ANALYST,))

    response = api.request(
        "POST",
        "/api/v1/service-accounts",
        json={"name": "Bank", "scopes": ["transactions:read"]},
    )

    assert response.status_code == 403
    assert api.accounts.added == []


def test_management_requires_authentication() -> None:
    api = Api(authenticated=False)

    response = api.request("GET", "/api/v1/service-accounts")

    assert response.status_code == 401


def test_get_and_list_service_accounts_without_secret_hashes() -> None:
    account = make_service_account()
    api = Api(accounts=(account,))

    single = api.request("GET", f"/api/v1/service-accounts/{account.id.value}")
    page = api.request("GET", "/api/v1/service-accounts?limit=10")

    assert single.status_code == 200
    assert single.json()["client_id"] == CLIENT_ID
    assert single.json()["status"] == "ACTIVE"
    assert len(single.json()["active_secrets"]) == 1
    assert "hash" not in single.text
    assert page.status_code == 200
    assert page.json()["has_more"] is False
    assert [item["client_id"] for item in page.json()["service_accounts"]] == [
        CLIENT_ID
    ]


def test_missing_service_account_is_404() -> None:
    api = Api()

    response = api.request(
        "GET", "/api/v1/service-accounts/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


def test_rotate_returns_new_secret_and_previous_expiry() -> None:
    account = make_service_account()
    api = Api(accounts=(account,))

    response = api.request(
        "POST", f"/api/v1/service-accounts/{account.id.value}/secrets"
    )

    assert response.status_code == 201
    assert response.json()["client_secret"] == "plain-secret-new"
    assert response.json()["previous_secret_expires_at"] is not None
    assert response.headers["cache-control"] == "no-store"


def test_revoke_then_rotate_and_revoke_again_conflict() -> None:
    account = make_service_account()
    api = Api(accounts=(account,))

    first = api.request("DELETE", f"/api/v1/service-accounts/{account.id.value}")
    rotate = api.request("POST", f"/api/v1/service-accounts/{account.id.value}/secrets")
    second = api.request("DELETE", f"/api/v1/service-accounts/{account.id.value}")

    assert first.status_code == 204
    assert rotate.status_code == 409
    assert second.status_code == 409


# ---------- oauth token ----------


def test_client_credentials_in_body_get_token() -> None:
    api = Api(accounts=(make_service_account(),))

    response = api.token(credentials_form())

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "machine-token",
        "token_type": "Bearer",
        "expires_in": 900,
        "scope": "transactions:read transactions:write",
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_client_credentials_via_basic_auth_get_token() -> None:
    api = Api(accounts=(make_service_account(),))

    response = api.token(
        {"grant_type": "client_credentials", "scope": "transactions:read"},
        headers={"Authorization": basic(CLIENT_ID, PLAIN_SECRET)},
    )

    assert response.status_code == 200
    assert response.json()["scope"] == "transactions:read"


@pytest.mark.parametrize(
    "form",
    [
        credentials_form(client_secret="wrong"),
        credentials_form(client_id="sa_" + "z" * 32),
        credentials_form(client_id="not-a-client"),
        {"grant_type": "client_credentials"},
    ],
)
def test_bad_client_credentials_are_invalid_client(form) -> None:
    api = Api(accounts=(make_service_account(),))

    response = api.token(form)

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_client"}
    assert response.headers["www-authenticate"].startswith("Basic")
    assert api.tokens.calls == []


def test_revoked_client_is_invalid_client() -> None:
    account = make_service_account()
    account.revoke(NOW)
    api = Api(accounts=(account,))

    response = api.token(credentials_form())

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_client"}


@pytest.mark.parametrize(
    ("form", "error"),
    [
        (credentials_form(grant_type="password"), "unsupported_grant_type"),
        ({"client_id": CLIENT_ID, "client_secret": PLAIN_SECRET}, "invalid_request"),
        (credentials_form(scope="ADMIN"), "invalid_scope"),
        (credentials_form(scope="webhooks:manage"), "invalid_scope"),
    ],
)
def test_oauth_request_errors(form, error: str) -> None:
    api = Api(accounts=(make_service_account(),))

    response = api.token(form)

    assert response.status_code == 400
    assert response.json() == {"error": error}


def test_credentials_in_header_and_body_are_rejected() -> None:
    api = Api(accounts=(make_service_account(),))

    response = api.token(
        credentials_form(), headers={"Authorization": basic(CLIENT_ID, PLAIN_SECRET)}
    )

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request"}


def test_malformed_basic_header_is_invalid_client() -> None:
    api = Api(accounts=(make_service_account(),))

    response = api.token(
        {"grant_type": "client_credentials"},
        headers={"Authorization": "Basic not-base64!"},
    )

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_client"}


def test_repeated_parameter_is_invalid_request() -> None:
    api = Api(accounts=(make_service_account(),))

    response = api.token(
        urlencode(credentials_form()) + "&grant_type=client_credentials"
    )

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request"}


def test_json_body_is_invalid_request() -> None:
    api = Api(accounts=(make_service_account(),))

    response = api.request("POST", "/api/v1/oauth/token", json=credentials_form())

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request"}


def test_oversized_body_is_invalid_request() -> None:
    api = Api(accounts=(make_service_account(),))

    response = api.token(credentials_form(scope="x" * 5000))

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request"}
    assert api.tokens.calls == []


def test_expires_in_is_relative_to_now() -> None:
    api = Api(accounts=(make_service_account(),))
    later = FixedClock(NOW + timedelta(minutes=5))
    api.app.dependency_overrides[get_clock] = lambda: later

    response = api.token(credentials_form())

    assert response.status_code == 200
    assert response.json()["expires_in"] == 600


def test_token_endpoint_is_documented_as_form() -> None:
    operation = Api().app.openapi()["paths"]["/api/v1/oauth/token"]["post"]

    assert FORM in operation["requestBody"]["content"]
