import asyncio
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.messages.invitation_email_requested import (
    InvitationEmailRequested,
)
from identity.domain.aggregates.invitation import Invitation
from identity.domain.enums.role import EmployeeRole
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId
from identity.infrastructure.outbox.invitation_email_worker import (
    InvitationEmailWorker,
)
from identity.infrastructure.persistence.data_mapper.invitation_mapper import (
    InvitationMapper,
)
from identity.infrastructure.persistence.models.invitation import InvitationModel
from identity.infrastructure.persistence.models.outbox_message import (
    OutboxMessageModel,
)
from identity.infrastructure.security.hmac_invitation_tokens import HmacInvitationTokens

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0

    async def __aenter__(self) -> "FakeTransaction":  # noqa: PYI034
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.commits += 1


class FakeOutboxSession:
    def __init__(self, row: OutboxMessageModel) -> None:
        self.row = row
        self.transaction = FakeTransaction()
        self.statement = None

    async def __aenter__(self) -> "FakeOutboxSession":  # noqa: PYI034
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        pass

    def begin(self) -> FakeTransaction:
        return self.transaction

    async def scalar(self, statement):
        self.statement = statement
        return self.row


class FakeDeliverySession:
    def __init__(self, invitation: InvitationModel) -> None:
        self.invitation = invitation
        self.rollbacks = 0

    async def __aenter__(self) -> "FakeDeliverySession":  # noqa: PYI034
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        pass

    async def get(self, model, invitation_id):
        assert model is InvitationModel
        assert invitation_id == self.invitation.id
        return self.invitation

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[Email, str]] = []

    async def send(self, email: Email, plain_token: str) -> None:
        if self.fail:
            raise OSError("SMTP unavailable")
        self.sent.append((email, plain_token))


class FakeSessionFactory:
    def __init__(self, *sessions: object) -> None:
        self._sessions: Iterator[object] = iter(sessions)

    def __call__(self) -> AsyncSession:
        return cast(AsyncSession, next(self._sessions))


def make_worker(
    sender: FakeSender,
    outbox_session: FakeOutboxSession,
    delivery_session: FakeDeliverySession,
) -> tuple[InvitationEmailWorker, HmacInvitationTokens]:
    tokens = HmacInvitationTokens(
        signing_key=b"test-invitation-signing-key-32-bytes",
        lifetime=timedelta(days=7),
    )
    worker = InvitationEmailWorker(
        session_factory=cast(
            async_sessionmaker[AsyncSession],
            FakeSessionFactory(outbox_session, delivery_session),
        ),
        clock=FixedClock(),
        token_issuer=tokens,
        token_verifier=tokens,
        email_sender=sender,
    )
    return worker, tokens


def make_records() -> tuple[OutboxMessageModel, InvitationModel]:
    invitation_id = InvitationId.new()
    tokens = HmacInvitationTokens(
        signing_key=b"test-invitation-signing-key-32-bytes",
        lifetime=timedelta(days=7),
    )
    issued = tokens.issue(invitation_id, NOW)
    invitation = Invitation.issue(
        invitation_id=invitation_id,
        invited_by=EmployeeId.new(),
        invited_email=Email("employee@example.com"),
        roles=(EmployeeRole.AUDITOR,),
        token_hash=issued.token_hash,
        created_at=NOW,
        expires_at=issued.expires_at,
    )
    row = OutboxMessageModel(
        message_id=uuid4(),
        message_type=InvitationEmailRequested.__name__,
        version=1,
        payload={
            "invitation_id": str(invitation_id.value),
            "recipient_email": "employee@example.com",
        },
        created_at=NOW,
        published_at=None,
        delivery_attempts=0,
        next_attempt_at=None,
    )
    return row, InvitationMapper.to_model(invitation)


def test_worker_delivers_invitation_and_marks_outbox_row() -> None:
    row, invitation = make_records()
    outbox = FakeOutboxSession(row)
    delivery = FakeDeliverySession(invitation)
    sender = FakeSender()
    worker, tokens = make_worker(sender, outbox, delivery)

    result = asyncio.run(worker.process_one())

    assert result == "delivered"
    assert sender.sent == [
        (
            Email("employee@example.com"),
            tokens.derive_token(InvitationId(invitation.id)),
        )
    ]
    assert row.published_at == NOW
    assert row.delivery_attempts == 0
    assert outbox.transaction.commits == 1
    assert delivery.rollbacks == 1
    assert outbox.statement is not None
    sql = str(outbox.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "next_attempt_at" in sql


@pytest.mark.parametrize(("previous_attempts", "delay_seconds"), [(0, 2), (20, 300)])
def test_worker_schedules_retry_when_smtp_fails(
    previous_attempts: int, delay_seconds: int
) -> None:
    row, invitation = make_records()
    row.delivery_attempts = previous_attempts
    outbox = FakeOutboxSession(row)
    delivery = FakeDeliverySession(invitation)
    sender = FakeSender(fail=True)
    worker, _ = make_worker(sender, outbox, delivery)

    result = asyncio.run(worker.process_one())

    assert result == "retry"
    assert row.published_at is None
    assert row.delivery_attempts == previous_attempts + 1
    assert row.next_attempt_at == NOW + timedelta(seconds=delay_seconds)
    assert outbox.transaction.commits == 1
    assert delivery.rollbacks == 1
    assert sender.sent == []


def test_worker_rejects_malformed_payload_without_marking_delivered() -> None:
    row, invitation = make_records()
    row.payload = {"invitation_id": "bad", "recipient_email": 123}
    outbox = FakeOutboxSession(row)
    delivery = FakeDeliverySession(invitation)
    worker, _ = make_worker(FakeSender(), outbox, delivery)

    result = asyncio.run(worker.process_one())

    assert result == "retry"
    assert row.published_at is None
    assert row.delivery_attempts == 1
    assert outbox.transaction.commits == 1
