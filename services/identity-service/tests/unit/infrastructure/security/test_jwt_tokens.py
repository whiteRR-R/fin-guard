import asyncio
from datetime import datetime, timedelta, timezone
from typing import cast

import jwt
import pytest

from identity.application.authentication.authenticate_access_token import (
    AuthenticateAccessToken,
)
from identity.application.commands.refresh_access_token.command import (
    RefreshAccessTokenCommand,
)
from identity.application.commands.refresh_access_token.handler import (
    RefreshAccessTokenHandler,
)
from identity.application.exceptions import (
    AuthenticationError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
)
from identity.application.messages.refresh_token_reuse_detected import (
    RefreshTokenReuseDetected,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.enums.role import EmployeeRole
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)
from identity.infrastructure.security.jwt_access_tokens import JwtAccessTokens
from identity.infrastructure.security.jwt_refresh_tokens import JwtRefreshTokens
from tests.unit.application.doubles import (
    EmployeeRepositoryFake,
    FixedClock,
    OutboxRepositoryFake,
    RefreshSessionRepositoryFake,
    UnitOfWorkFake,
)
from tests.unit.application.factories import make_employee, make_refresh_session
from tests.unit.application.session_support import (
    SessionState,
    TransactionalStore,
    TransactionalUnitOfWork,
    make_session_repository,
)

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
ACCESS_KEY = b"a" * 32
REFRESH_KEY = b"r" * 32
ISSUER = "fin-guard-identity"
ACCESS_AUDIENCE = "fin-guard-access"
REFRESH_AUDIENCE = "fin-guard-refresh"


@pytest.fixture
def employee_and_session() -> tuple[EmployeeAccount, RefreshSession]:
    employee = make_employee(
        "employee@example.com",
        roles=(EmployeeRole.ADMIN, EmployeeRole.AUDITOR),
    )
    session = make_refresh_session(employee.id, now=NOW)
    return employee, session


@pytest.fixture
def access_tokens() -> JwtAccessTokens:
    return JwtAccessTokens(
        signing_key=ACCESS_KEY,
        lifetime=timedelta(minutes=15),
        issuer=ISSUER,
        audience=ACCESS_AUDIENCE,
    )


@pytest.fixture
def refresh_tokens() -> JwtRefreshTokens:
    return JwtRefreshTokens(
        signing_key=REFRESH_KEY,
        lifetime=timedelta(days=30),
        issuer=ISSUER,
        audience=REFRESH_AUDIENCE,
        clock=FixedClock(NOW),
    )


def test_access_token_round_trip(
    access_tokens: JwtAccessTokens,
    employee_and_session: tuple[EmployeeAccount, RefreshSession],
) -> None:
    employee, session = employee_and_session

    issued = access_tokens.issue(employee.id, session.id, employee.roles, NOW)
    claims = access_tokens.verify(issued.plain_token)

    assert claims.employee_id == employee.id
    assert claims.sid == session.id
    assert claims.roles == employee.roles
    assert claims.expires_at == NOW + timedelta(minutes=15)
    assert issued.expires_at == claims.expires_at
    assert issued.plain_token not in repr(issued)
    assert jwt.get_unverified_header(issued.plain_token)["alg"] == "HS256"


def test_refresh_tokens_are_unique_and_only_hash_is_stored(
    refresh_tokens: JwtRefreshTokens,
) -> None:
    session_id = RefreshSessionId.new()

    first = refresh_tokens.issue(session_id)
    second = refresh_tokens.issue(session_id)

    assert first.plain_token != second.plain_token
    assert first.token_hash != second.token_hash
    assert first.plain_token not in repr(first)
    assert first.token_hash.value not in repr(first)
    assert refresh_tokens.matches_hash(first.plain_token, first.token_hash)
    assert not refresh_tokens.matches_hash(second.plain_token, first.token_hash)
    assert refresh_tokens.verify(first.plain_token).session_id == session_id
    assert refresh_tokens.verify(first.plain_token).expires_at == NOW + timedelta(
        days=30
    )
    assert jwt.get_unverified_header(first.plain_token)["alg"] == "HS256"


def test_access_token_cannot_be_used_as_refresh_token_even_with_shared_key(
    access_tokens: JwtAccessTokens,
    employee_and_session: tuple[EmployeeAccount, RefreshSession],
) -> None:
    employee, session = employee_and_session
    refresh = JwtRefreshTokens(
        signing_key=ACCESS_KEY,
        lifetime=timedelta(days=30),
        issuer=ISSUER,
        audience=ACCESS_AUDIENCE,
        clock=FixedClock(NOW),
    )
    token = access_tokens.issue(employee.id, session.id, employee.roles, NOW)

    with pytest.raises(InvalidRefreshTokenError):
        refresh.verify(token.plain_token)


def test_refresh_token_cannot_be_used_as_access_token_even_with_shared_key(
    refresh_tokens: JwtRefreshTokens,
) -> None:
    access = JwtAccessTokens(
        signing_key=REFRESH_KEY,
        lifetime=timedelta(minutes=15),
        issuer=ISSUER,
        audience=REFRESH_AUDIENCE,
    )
    token = refresh_tokens.issue(RefreshSessionId.new())

    with pytest.raises(AuthenticationError):
        access.verify(token.plain_token)


@pytest.mark.parametrize("change", ["wrong_key", "wrong_audience", "wrong_issuer"])
def test_access_verifier_rejects_wrong_configuration(
    access_tokens: JwtAccessTokens,
    employee_and_session: tuple[EmployeeAccount, RefreshSession],
    change: str,
) -> None:
    employee, session = employee_and_session
    token = access_tokens.issue(employee.id, session.id, employee.roles, NOW)
    verifier = JwtAccessTokens(
        signing_key=b"x" * 32 if change == "wrong_key" else ACCESS_KEY,
        lifetime=timedelta(minutes=15),
        issuer="other-issuer" if change == "wrong_issuer" else ISSUER,
        audience="other-audience" if change == "wrong_audience" else ACCESS_AUDIENCE,
    )

    with pytest.raises(AuthenticationError):
        verifier.verify(token.plain_token)


@pytest.mark.parametrize("change", ["wrong_key", "wrong_audience", "wrong_issuer"])
def test_refresh_verifier_rejects_wrong_configuration(
    refresh_tokens: JwtRefreshTokens,
    change: str,
) -> None:
    token = refresh_tokens.issue(RefreshSessionId.new())
    verifier = JwtRefreshTokens(
        signing_key=b"x" * 32 if change == "wrong_key" else REFRESH_KEY,
        lifetime=timedelta(days=30),
        issuer="other-issuer" if change == "wrong_issuer" else ISSUER,
        audience="other-audience" if change == "wrong_audience" else REFRESH_AUDIENCE,
        clock=FixedClock(NOW),
    )

    with pytest.raises(InvalidRefreshTokenError):
        verifier.verify(token.plain_token)


def test_verifiers_reject_unsigned_and_wrong_algorithm_tokens(
    access_tokens: JwtAccessTokens,
    refresh_tokens: JwtRefreshTokens,
) -> None:
    access_payload = {
        "iss": ISSUER,
        "aud": ACCESS_AUDIENCE,
        "sub": str(make_employee("employee@example.com").id.value),
        "sid": str(RefreshSessionId.new().value),
        "roles": [EmployeeRole.ADMIN.value],
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=15)).timestamp()),
        "token_use": "access",
    }
    refresh_payload = {
        "iss": ISSUER,
        "aud": REFRESH_AUDIENCE,
        "sid": str(RefreshSessionId.new().value),
        "jti": str(RefreshSessionId.new().value),
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(days=30)).timestamp()),
        "token_use": "refresh",
    }

    for algorithm, key in [("none", ""), ("HS512", b"a" * 64)]:
        access_token = jwt.encode(access_payload, key, algorithm=algorithm)
        with pytest.raises(AuthenticationError):
            access_tokens.verify(access_token)

    for algorithm, key in [("none", ""), ("HS512", b"r" * 64)]:
        refresh_token = jwt.encode(refresh_payload, key, algorithm=algorithm)
        with pytest.raises(InvalidRefreshTokenError):
            refresh_tokens.verify(refresh_token)


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("sub", "invalid-uuid"),
        ("sid", "invalid-uuid"),
        ("roles", ["UNKNOWN"]),
        ("roles", ["ADMIN", "ADMIN"]),
        ("roles", "ADMIN"),
        ("exp", "invalid"),
        ("iat", True),
        ("token_use", "refresh"),
    ],
)
def test_access_verifier_rejects_malformed_signed_claims(
    access_tokens: JwtAccessTokens,
    employee_and_session: tuple[EmployeeAccount, RefreshSession],
    claim: str,
    value: object,
) -> None:
    employee, session = employee_and_session
    issued = access_tokens.issue(employee.id, session.id, employee.roles, NOW)
    payload = jwt.decode(
        issued.plain_token,
        ACCESS_KEY,
        algorithms=["HS256"],
        audience=ACCESS_AUDIENCE,
        issuer=ISSUER,
        options={"verify_exp": False, "verify_iat": False},
    )
    payload[claim] = value

    with pytest.raises(AuthenticationError):
        access_tokens.verify(jwt.encode(payload, ACCESS_KEY, algorithm="HS256"))


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("sid", "invalid-uuid"),
        ("jti", "invalid-uuid"),
        ("exp", "invalid"),
        ("iat", True),
        ("token_use", "access"),
    ],
)
def test_refresh_verifier_rejects_malformed_signed_claims(
    refresh_tokens: JwtRefreshTokens,
    claim: str,
    value: object,
) -> None:
    issued = refresh_tokens.issue(RefreshSessionId.new())
    payload = jwt.decode(
        issued.plain_token,
        REFRESH_KEY,
        algorithms=["HS256"],
        audience=REFRESH_AUDIENCE,
        issuer=ISSUER,
        options={"verify_exp": False, "verify_iat": False},
    )
    payload[claim] = value

    with pytest.raises(InvalidRefreshTokenError):
        refresh_tokens.verify(jwt.encode(payload, REFRESH_KEY, algorithm="HS256"))


@pytest.mark.parametrize("key", [b"short", "short", b""])
def test_signing_key_must_be_strong(key: bytes | str) -> None:
    with pytest.raises(ValueError):
        JwtAccessTokens(cast(bytes, key), timedelta(minutes=15), ISSUER, ACCESS_AUDIENCE)
    with pytest.raises(ValueError):
        JwtRefreshTokens(
            cast(bytes, key),
            timedelta(days=30),
            ISSUER,
            REFRESH_AUDIENCE,
            FixedClock(NOW),
        )


def test_authentication_rejects_expired_signed_access_token(
    access_tokens: JwtAccessTokens,
    employee_and_session: tuple[EmployeeAccount, RefreshSession],
) -> None:
    employee, session = employee_and_session
    issued = access_tokens.issue(employee.id, session.id, employee.roles, NOW)
    authenticator = AuthenticateAccessToken(
        clock=FixedClock(NOW + timedelta(minutes=15)),
        uow=UnitOfWorkFake(),
        employees=EmployeeRepositoryFake((employee,)),
        refresh_sessions=RefreshSessionRepositoryFake(
            active_at=NOW,
            sessions=(session,),
        ),
        access_token_verifier=access_tokens,
    )

    with pytest.raises(AuthenticationError, match="expired"):
        asyncio.run(authenticator.execute(issued.plain_token))


def test_refresh_hash_rejects_other_token(refresh_tokens: JwtRefreshTokens) -> None:
    issued = refresh_tokens.issue(RefreshSessionId.new())

    assert not refresh_tokens.matches_hash("another-token", issued.token_hash)
    assert not refresh_tokens.matches_hash(
        issued.plain_token, RefreshTokenHash("0" * 64)
    )
    assert not refresh_tokens.matches_hash(
        issued.plain_token, RefreshTokenHash("не hex")
    )


def test_authentication_uses_current_roles_from_database(
    access_tokens: JwtAccessTokens,
    employee_and_session: tuple[EmployeeAccount, RefreshSession],
) -> None:
    employee, session = employee_and_session
    token = access_tokens.issue(employee.id, session.id, employee.roles, NOW)
    employee.revoke_role(EmployeeRole.ADMIN)
    authenticator = AuthenticateAccessToken(
        clock=FixedClock(NOW + timedelta(minutes=1)),
        uow=UnitOfWorkFake(),
        employees=EmployeeRepositoryFake((employee,)),
        refresh_sessions=RefreshSessionRepositoryFake(
            active_at=NOW,
            sessions=(session,),
        ),
        access_token_verifier=access_tokens,
    )

    actor = asyncio.run(authenticator.execute(token.plain_token))

    assert actor.roles == frozenset({EmployeeRole.AUDITOR})
    assert access_tokens.verify(token.plain_token).roles == frozenset(
        {EmployeeRole.ADMIN, EmployeeRole.AUDITOR}
    )


def test_real_refresh_tokens_rotate_and_detect_reuse(
    access_tokens: JwtAccessTokens,
    refresh_tokens: JwtRefreshTokens,
) -> None:
    employee = make_employee("employee@example.com")
    session_id = RefreshSessionId.new()
    initial_token = refresh_tokens.issue(session_id)
    session = RefreshSession.start(
        session_id=session_id,
        employee_id=employee.id,
        refresh_token_hash=initial_token.token_hash,
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=30),
    )
    store = TransactionalStore(SessionState(sessions={session_id: session}))
    uow = TransactionalUnitOfWork(store)
    sessions = make_session_repository(store, uow)
    outbox = OutboxRepositoryFake()
    handler = RefreshAccessTokenHandler(
        uow=uow,
        clock=FixedClock(NOW),
        access_token_issuer=access_tokens,
        refresh_token_issuer=refresh_tokens,
        refresh_token_verifier=refresh_tokens,
        refresh_session_repository=sessions,
        employee_repository=EmployeeRepositoryFake((employee,)),
        outbox_repository=outbox,
    )

    rotated = asyncio.run(
        handler.execute(RefreshAccessTokenCommand(initial_token.plain_token))
    )

    assert rotated.refresh_token != initial_token.plain_token
    assert refresh_tokens.matches_hash(
        rotated.refresh_token, store.state.sessions[session_id].refresh_token_hash
    )
    assert access_tokens.verify(rotated.access_token).employee_id == employee.id
    assert store.state.history[session_id] == [initial_token.token_hash]
    assert uow.commit_count == 1

    with pytest.raises(RefreshTokenReuseError):
        asyncio.run(
            handler.execute(RefreshAccessTokenCommand(initial_token.plain_token))
        )

    assert store.state.sessions[session_id].revoked_at == NOW
    assert len(outbox.added) == 1
    assert isinstance(outbox.added[0], RefreshTokenReuseDetected)
    assert uow.commit_count == 2
