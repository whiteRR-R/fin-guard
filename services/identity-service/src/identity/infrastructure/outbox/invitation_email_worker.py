import logging
from datetime import timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.email_delivery.deliver_invitation_email import (
    DeliverInvitationEmail,
)
from identity.application.messages.invitation_email_requested import (
    InvitationEmailRequested,
)
from identity.application.ports.clock import Clock
from identity.application.ports.email_sender import EmailSender
from identity.application.ports.security.invitation_token_issuer import (
    InvitationTokenIssuer,
)
from identity.application.ports.security.invitation_token_verifier import (
    InvitationTokenVerifier,
)
from identity.infrastructure.persistence.models.outbox_message import (
    OutboxMessageModel,
)
from identity.infrastructure.persistence.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

logger = logging.getLogger(__name__)


class InvitationEmailWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Clock,
        token_issuer: InvitationTokenIssuer,
        token_verifier: InvitationTokenVerifier,
        email_sender: EmailSender,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._token_issuer = token_issuer
        self._token_verifier = token_verifier
        self._email_sender = email_sender

    async def process_one(self) -> Literal["delivered", "retry", "idle"]:
        async with (
            self._session_factory() as outbox_session,
            outbox_session.begin(),
        ):
            now = self._clock.now()
            statement = (
                select(OutboxMessageModel)
                .where(
                    OutboxMessageModel.message_type
                    == InvitationEmailRequested.__name__,
                    OutboxMessageModel.version == 1,
                    OutboxMessageModel.published_at.is_(None),
                    or_(
                        OutboxMessageModel.next_attempt_at.is_(None),
                        OutboxMessageModel.next_attempt_at <= now,
                    ),
                )
                .order_by(
                    OutboxMessageModel.created_at,
                    OutboxMessageModel.message_id,
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            row = await outbox_session.scalar(statement)
            if row is None:
                return "idle"

            try:
                message = self._decode(row)
                await self._deliver(message)
            except Exception as error:  # noqa: BLE001 - retry adapter failures
                row.delivery_attempts += 1
                delay = min(2 ** min(row.delivery_attempts, 9), 300)
                row.next_attempt_at = now + timedelta(seconds=delay)
                logger.warning(
                    "Invitation delivery deferred for outbox message %s (%s)",
                    row.message_id,
                    type(error).__name__,
                )
                return "retry"

            row.published_at = self._clock.now()
            row.next_attempt_at = None
            return "delivered"

    async def _deliver(self, message: InvitationEmailRequested) -> None:
        # Delivery's read-only Unit of Work rolls back on exit. A separate session
        # keeps the outbox row locked until the delivery result is committed.
        async with self._session_factory() as session:
            handler = DeliverInvitationEmail(
                uow=SqlAlchemyUnitOfWork(session),
                clock=self._clock,
                invitations=InvitationRepository(session),
                token_issuer=self._token_issuer,
                token_verifier=self._token_verifier,
                email_sender=self._email_sender,
            )
            await handler.execute(message)

    @staticmethod
    def _decode(row: OutboxMessageModel) -> InvitationEmailRequested:
        invitation_id = row.payload.get("invitation_id")
        recipient_email = row.payload.get("recipient_email")
        if not isinstance(invitation_id, str) or not isinstance(recipient_email, str):
            raise TypeError("Invalid invitation email outbox payload")

        return InvitationEmailRequested(
            message_id=row.message_id,
            created_at=row.created_at,
            invitation_id=UUID(invitation_id),
            recipient_email=recipient_email,
        )
