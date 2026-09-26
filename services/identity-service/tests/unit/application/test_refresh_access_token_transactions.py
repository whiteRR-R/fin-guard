import asyncio

import pytest

from identity.application.commands.refresh_access_token.command import (
    RefreshAccessTokenCommand,
)
from identity.application.commands.refresh_access_token.result import (
    RefreshAccessTokenResult,
)
from identity.application.exceptions import RefreshTokenReuseError
from tests.unit.application.refresh_access_token_support import (
    NOW,
    OLD_HASH,
    OLD_TOKEN,
    make_context,
)


@pytest.mark.parametrize("failure", ["save", "commit", "access_issuer"])
def test_failed_rotation_rolls_back_token_and_history(failure: str) -> None:
    context = make_context()
    if failure == "save":
        context.sessions.save.side_effect = RuntimeError("Save failed")
    elif failure == "commit":
        context.uow.fail_commit = True
    else:
        context.access_issuer.issue.side_effect = RuntimeError("Issue failed")

    with pytest.raises(RuntimeError):
        context.execute()

    assert context.session.refresh_token_hash == OLD_HASH
    assert context.store.state.history == {}
    assert context.store.state.messages == []
    assert context.uow.commit_count == 0
    assert context.uow.rollback_count == 1


@pytest.mark.parametrize("failure", ["outbox", "commit"])
def test_failed_reuse_audit_rolls_back_revocation(failure: str) -> None:
    context = make_context()
    context.execute()
    if failure == "outbox":
        context.outbox.add.side_effect = RuntimeError("Outbox failed")
    else:
        context.uow.fail_commit = True

    with pytest.raises(RuntimeError):
        context.execute()

    assert context.session.revoked_at is None
    assert context.store.state.messages == []
    assert context.uow.commit_count == 1
    assert context.uow.rollback_count == 1


def test_concurrent_requests_with_same_token_cannot_both_succeed() -> None:
    async def run() -> None:
        first = make_context()
        second = make_context(employee=first.employee, store=first.store)

        outcomes = await asyncio.gather(
            first.handler.execute(RefreshAccessTokenCommand(OLD_TOKEN)),
            second.handler.execute(RefreshAccessTokenCommand(OLD_TOKEN)),
            return_exceptions=True,
        )

        successes = [
            result for result in outcomes if isinstance(result, RefreshAccessTokenResult)
        ]
        reuse_errors = [
            result for result in outcomes if isinstance(result, RefreshTokenReuseError)
        ]
        assert len(successes) == 1
        assert len(reuse_errors) == 1
        assert first.session.revoked_at == NOW
        assert len(first.store.state.messages) == 1
        assert first.store.state.history[first.session_id] == [OLD_HASH]

    asyncio.run(run())
