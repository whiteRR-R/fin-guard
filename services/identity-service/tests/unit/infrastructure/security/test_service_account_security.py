from datetime import datetime, timedelta, timezone

import jwt
import pytest

from identity.application.exceptions import AuthenticationError
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.scope import MachineScope
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import RefreshSessionId
from identity.domain.value_objects.service_account import (
    ClientId,
    ClientSecretHash,
    ServiceAccountId,
)
from identity.infrastructure.security.hmac_client_credentials import (
    HmacClientCredentials,
)
from identity.infrastructure.security.jwt_access_tokens import JwtAccessTokens
from identity.infrastructure.security.jwt_machine_tokens import JwtMachineTokens
from tests.unit.application.doubles import FixedClock

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
KEY = b"k" * 32
SIGNING_KEY = b"s" * 32
ISSUER = "identity-service"
AUDIENCE = "finguard-api"
LIFETIME = timedelta(minutes=15)
CLIENT_ID = ClientId("sa_" + "a" * 32)
SCOPES = frozenset({MachineScope.TRANSACTIONS_WRITE, MachineScope.RISK_RESULTS_READ})


def machine_tokens(now: datetime = NOW, key: bytes = SIGNING_KEY) -> JwtMachineTokens:
    return JwtMachineTokens(
        signing_key=key,
        lifetime=LIFETIME,
        issuer=ISSUER,
        audience=AUDIENCE,
        clock=FixedClock(now),
    )


def access_tokens() -> JwtAccessTokens:
    return JwtAccessTokens(
        signing_key=SIGNING_KEY,
        lifetime=LIFETIME,
        issuer=ISSUER,
        audience=AUDIENCE,
    )


def issue_machine_token(tokens: JwtMachineTokens | None = None) -> str:
    return (
        (tokens or machine_tokens())
        .issue(
            service_account_id=ServiceAccountId.new(),
            client_id=CLIENT_ID,
            scopes=SCOPES,
            issued_at=NOW,
        )
        .plain_token
    )


# ---------- client credentials ----------


def test_generated_client_ids_are_valid_and_unique() -> None:
    credentials = HmacClientCredentials(KEY)

    client_ids = {credentials.new_client_id() for _ in range(50)}

    assert len(client_ids) == 50
    assert all(isinstance(client_id, ClientId) for client_id in client_ids)


def test_secret_is_random_and_only_its_hash_is_stored() -> None:
    credentials = HmacClientCredentials(KEY)

    first = credentials.issue_secret()
    second = credentials.issue_secret()

    assert first.plain_secret != second.plain_secret
    assert first.secret_hash != second.secret_hash
    assert first.plain_secret.startswith("fgs_")
    assert len(first.plain_secret) >= 40
    assert first.plain_secret not in first.secret_hash.value
    assert first.secret_hash.value.startswith("hmac-sha256$")
    assert first.plain_secret not in repr(first)


def test_secret_matches_only_its_own_hash() -> None:
    credentials = HmacClientCredentials(KEY)
    issued = credentials.issue_secret()

    assert credentials.matches(issued.plain_secret, issued.secret_hash) is True
    assert credentials.matches(issued.plain_secret + "x", issued.secret_hash) is False
    assert (
        credentials.matches(issued.plain_secret, credentials.issue_secret().secret_hash)
        is False
    )


def test_hash_depends_on_server_key() -> None:
    issued = HmacClientCredentials(KEY).issue_secret()

    assert (
        HmacClientCredentials(b"o" * 32).matches(
            issued.plain_secret, issued.secret_hash
        )
        is False
    )


@pytest.mark.parametrize("plain_secret", ["", "x" * 257, None, 42])
def test_invalid_presented_secrets_never_match(plain_secret) -> None:
    credentials = HmacClientCredentials(KEY)

    assert credentials.matches(plain_secret, ClientSecretHash("hash")) is False


@pytest.mark.parametrize("key", [b"short", "k" * 32])
def test_hash_key_must_be_strong_bytes(key) -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        HmacClientCredentials(key)


# ---------- machine tokens ----------


def test_machine_token_round_trip() -> None:
    tokens = machine_tokens()
    service_account_id = ServiceAccountId.new()

    issued = tokens.issue(
        service_account_id=service_account_id,
        client_id=CLIENT_ID,
        scopes=SCOPES,
        issued_at=NOW,
    )
    claims = tokens.verify(issued.plain_token)

    assert issued.expires_at == NOW + LIFETIME
    assert claims.service_account_id == service_account_id
    assert claims.client_id == CLIENT_ID
    assert claims.scopes == SCOPES
    assert claims.expires_at == NOW + LIFETIME


def test_machine_token_payload_carries_scopes_not_roles() -> None:
    payload = jwt.decode(issue_machine_token(), options={"verify_signature": False})

    assert payload["token_use"] == "machine"
    assert payload["sub"] == CLIENT_ID.value
    assert payload["scope"] == "risk-results:read transactions:write"
    assert "roles" not in payload
    assert "sid" not in payload


def test_machine_token_is_not_accepted_as_employee_token() -> None:
    with pytest.raises(AuthenticationError):
        access_tokens().verify(issue_machine_token())


def test_employee_token_is_not_accepted_as_machine_token() -> None:
    employee_token = (
        access_tokens()
        .issue(
            employee_id=EmployeeId.new(),
            session_id=RefreshSessionId.new(),
            roles=frozenset({EmployeeRole.ADMIN}),
            issued_at=NOW,
        )
        .plain_token
    )

    with pytest.raises(AuthenticationError):
        machine_tokens().verify(employee_token)


def test_expired_machine_token_is_rejected() -> None:
    token = issue_machine_token()

    with pytest.raises(AuthenticationError):
        machine_tokens(now=NOW + LIFETIME).verify(token)
    assert machine_tokens(now=NOW + LIFETIME - timedelta(seconds=1)).verify(token)


def test_machine_token_signed_with_other_key_is_rejected() -> None:
    token = issue_machine_token(machine_tokens(key=b"x" * 32))

    with pytest.raises(AuthenticationError):
        machine_tokens().verify(token)


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "transactions:write ADMIN"},
        {"scope": ""},
        {"scope": "transactions:write transactions:write"},
        {"sub": "not-a-client-id"},
        {"said": "not-a-uuid"},
        {"token_use": "access"},
        {"aud": "other-audience"},
    ],
)
def test_machine_verifier_rejects_malformed_signed_claims(changes) -> None:
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": CLIENT_ID.value,
        "said": str(ServiceAccountId.new().value),
        "scope": "transactions:write",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + LIFETIME).timestamp()),
        "jti": "jti",
        "token_use": "machine",
        **changes,
    }
    token = jwt.encode(payload, SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError):
        machine_tokens().verify(token)


@pytest.mark.parametrize("lifetime", [timedelta(0), timedelta(hours=1, seconds=1)])
def test_machine_token_lifetime_is_short(lifetime: timedelta) -> None:
    with pytest.raises(ValueError, match="lifetime"):
        JwtMachineTokens(
            signing_key=SIGNING_KEY,
            lifetime=lifetime,
            issuer=ISSUER,
            audience=AUDIENCE,
            clock=FixedClock(NOW),
        )


def test_machine_token_requires_scopes() -> None:
    with pytest.raises(ValueError, match="scopes"):
        machine_tokens().issue(
            service_account_id=ServiceAccountId.new(),
            client_id=CLIENT_ID,
            scopes=frozenset(),
            issued_at=NOW,
        )
