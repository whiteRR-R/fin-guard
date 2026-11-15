import asyncio
from datetime import timedelta

import pytest

from identity.application.commands.issue_machine_access_token.command import (
    IssueMachineAccessTokenCommand,
)
from identity.application.commands.issue_machine_access_token.handler import (
    IssueMachineAccessTokenHandler,
)
from identity.application.exceptions import (
    AuthenticationError,
    InvalidClientError,
    InvalidScopeError,
)
from identity.domain.aggregates.service_account import (
    USAGE_RECORD_INTERVAL,
    ServiceAccount,
)
from identity.domain.enums.scope import MachineScope
from identity.domain.value_objects.service_account import ClientSecretId
from tests.unit.application.doubles import FixedClock, UnitOfWorkFake
from tests.unit.application.service_account_support import (
    CLIENT_ID,
    GRACE,
    NOW,
    PLAIN_SECRET,
    ClientCredentialsStub,
    MachineTokenIssuerStub,
    ServiceAccountRepositoryFake,
    hash_of,
    make_service_account,
)

WRITE = MachineScope.TRANSACTIONS_WRITE
READ = MachineScope.TRANSACTIONS_READ


class Context:
    def __init__(self, account: ServiceAccount | None = None, *, now=NOW) -> None:
        self.account = account if account is not None else make_service_account()
        self.uow = UnitOfWorkFake()
        self.accounts = ServiceAccountRepositoryFake((self.account,))
        self.verifier = ClientCredentialsStub()
        self.tokens = MachineTokenIssuerStub()
        self.handler = IssueMachineAccessTokenHandler(
            uow=self.uow,
            clock=FixedClock(now),
            service_accounts=self.accounts,
            secret_verifier=self.verifier,
            token_issuer=self.tokens,
        )

    def issue(
        self,
        *,
        client_id: str = CLIENT_ID,
        client_secret: str = PLAIN_SECRET,
        scopes: tuple[str, ...] | None = None,
    ):
        return asyncio.run(
            self.handler.execute(
                IssueMachineAccessTokenCommand(
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=scopes,
                )
            )
        )

    def assert_no_token(self) -> None:
        assert self.tokens.calls == []
        assert self.accounts.usage_saved == []
        assert self.uow.commit_count == 0


def test_valid_credentials_get_token_with_all_granted_scopes() -> None:
    context = Context()

    result = context.issue()

    assert result.access_token == "machine-token"
    assert result.token_type == "Bearer"
    assert result.scopes == (READ, WRITE)
    assert result.expires_at == NOW + timedelta(minutes=15)
    assert "machine-token" not in repr(result)
    assert context.tokens.calls == [
        {
            "service_account_id": context.account.id,
            "client_id": context.account.client_id,
            "scopes": frozenset({READ, WRITE}),
            "issued_at": NOW,
        }
    ]


def test_client_can_request_narrower_scopes() -> None:
    context = Context()

    result = context.issue(scopes=("transactions:read",))

    assert result.scopes == (READ,)


def test_client_cannot_request_scope_it_was_not_granted() -> None:
    context = Context(make_service_account(scopes=(READ,)))

    with pytest.raises(InvalidScopeError):
        context.issue(scopes=("transactions:write",))

    context.assert_no_token()


@pytest.mark.parametrize("scope", ["ADMIN", "transactions:delete", ""])
def test_unknown_scope_is_rejected(scope: str) -> None:
    context = Context()

    with pytest.raises(InvalidScopeError):
        context.issue(scopes=(scope,))

    context.assert_no_token()


def test_wrong_secret_is_invalid_client() -> None:
    context = Context()

    with pytest.raises(InvalidClientError):
        context.issue(client_secret="wrong-secret")

    context.assert_no_token()


def test_unknown_client_is_indistinguishable_from_wrong_secret() -> None:
    context = Context()

    with pytest.raises(InvalidClientError) as error:
        context.issue(client_id="sa_" + "z" * 32)

    assert str(error.value) == "Invalid client"
    assert len(context.verifier.verified) == 1
    context.assert_no_token()


def test_malformed_client_id_is_invalid_client() -> None:
    context = Context()

    with pytest.raises(InvalidClientError):
        context.issue(client_id="not-a-client-id")

    context.assert_no_token()


def test_invalid_client_is_an_authentication_error() -> None:
    assert issubclass(InvalidClientError, AuthenticationError)


def test_revoked_account_is_invalid_client() -> None:
    account = make_service_account()
    account.revoke(NOW)
    context = Context(account)

    with pytest.raises(InvalidClientError):
        context.issue()

    context.assert_no_token()


def test_previous_secret_works_only_during_grace_period() -> None:
    def rotated_account() -> ServiceAccount:
        account = make_service_account()
        account.rotate_secret(
            secret_id=ClientSecretId.new(),
            secret_hash=hash_of("plain-secret-2"),
            now=NOW,
            grace_period=GRACE,
        )
        return account

    in_grace = Context(rotated_account(), now=NOW + GRACE - timedelta(seconds=1))
    assert in_grace.issue(client_secret=PLAIN_SECRET).access_token
    assert in_grace.issue(client_secret="plain-secret-2").access_token

    after_grace = Context(rotated_account(), now=NOW + GRACE)
    with pytest.raises(InvalidClientError):
        after_grace.issue(client_secret=PLAIN_SECRET)
    assert after_grace.issue(client_secret="plain-secret-2").access_token


def test_usage_is_persisted_without_saving_whole_aggregate() -> None:
    context = Context()

    context.issue()

    assert context.account.last_used_at == NOW
    assert context.accounts.usage_saved == [context.account]
    assert context.accounts.saved == []
    assert context.uow.commit_count == 1


def test_repeated_usage_within_interval_writes_nothing() -> None:
    account = make_service_account()
    account.record_usage(NOW - USAGE_RECORD_INTERVAL / 2)
    context = Context(account)

    context.issue()

    assert context.accounts.usage_saved == []
    assert context.uow.commit_count == 0
    assert len(context.tokens.calls) == 1
