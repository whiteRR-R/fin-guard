from identity.application.exceptions import (
    InvitationDeliveryError,
    InvitationNotFoundError,
)
from identity.application.messages.invitation_email_requested import (
    InvitationEmailRequested,
)
from identity.application.ports.clock import Clock
from identity.application.ports.email_sender import EmailSender
from identity.application.ports.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.application.ports.security.invitation_token_issuer import (
    InvitationTokenIssuer,
)
from identity.application.ports.security.invitation_token_verifier import (
    InvitationTokenVerifier,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.enums.status import InvitationStatus
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.invitation_id import InvitationId


class DeliverInvitationEmail:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        invitations: InvitationRepository,
        token_issuer: InvitationTokenIssuer,
        token_verifier: InvitationTokenVerifier,
        email_sender: EmailSender,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._invitations = invitations
        self._token_issuer = token_issuer
        self._token_verifier = token_verifier
        self._email_sender = email_sender

    async def execute(self, message: InvitationEmailRequested) -> None:
        invitation_id = InvitationId(message.invitation_id)
        recipient_email = Email(message.recipient_email)

        async with self._uow:
            invitation = await self._invitations.get_by_id(invitation_id)

            if invitation is None:
                raise InvitationNotFoundError("Invitation not found")

            if recipient_email != invitation.invited_email:
                raise InvitationDeliveryError("Invitation recipient does not match")

            now = self._clock.now()

            if invitation.status is not InvitationStatus.PENDING:
                return

            if invitation.is_expired(now):
                return

            plain_token = self._token_issuer.derive_token(invitation.id)

            if not self._token_verifier.matches_hash(
                plain_token, invitation.token_hash
            ):
                raise InvitationDeliveryError("Invitation token does not match")

            await self._email_sender.send(invitation.invited_email, plain_token)
