from identity.application.commands.reissue_invitation.command import (
    ReissueInvitationCommand,
)
from identity.application.commands.reissue_invitation.result import (
    ReissueInvitationResult,
)
from identity.application.exceptions import (
    AuthenticationError,
    EmployeeIsNotInvitedError,
    EmployeeNotFoundError,
    InvitationCannotBeReissuedError,
    InvitationNotFoundError,
)
from identity.application.ports.clock import Clock
from identity.application.ports.email_sendler import EmailSender
from identity.application.ports.security.invitation_token_issuer import (
    InvitationTokenIssuer,
)
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.aggregates.invitation import Invitation
from identity.domain.enums.status import EmployeeStatus, InvitationStatus
from identity.domain.policies.employee_invite import EmployeeInvitePolicy
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId


class ReissueInvitationHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        email_sender: EmailSender,
        invitation_policy: EmployeeInvitePolicy,
        invitation_token_issuer: InvitationTokenIssuer,
    ):
        self._uow = uow
        self._clock = clock
        self._email_sender = email_sender
        self._invitation_policy = invitation_policy
        self._invitation_token_issuer = invitation_token_issuer

    async def execute(self, command: ReissueInvitationCommand):
        inviter_id = EmployeeId(command.inviter_id)
        invited_email = Email(command.employee_email)

        async with self._uow:
            inviter = await self._uow.employees.get_by_id(inviter_id)

            if inviter is None:
                raise AuthenticationError("Inviter not found")

            self._invitation_policy.ensure_allowed(inviter)

            invited_employee = await self._uow.employees.get_by_email(invited_email)

            if invited_employee is None:
                raise EmployeeNotFoundError("Employee not found")

            if invited_employee.status is not EmployeeStatus.INVITED:
                raise EmployeeIsNotInvitedError(
                    "Only an invited employee can receive a new invitation"
                )

            current_invitation = (
                await self._uow.invitations.get_latest_by_employee_email(invited_email)
            )

            if current_invitation is None:
                raise InvitationNotFoundError("Inivation not found")

            if current_invitation.status is InvitationStatus.ACCEPTED:
                raise InvitationCannotBeReissuedError(
                    "Accepted invitation cannot be reissued"
                )

            now = self._clock.now()

            if (
                current_invitation.status is InvitationStatus.PENDING
                and not current_invitation.is_expired(now)
            ):
                current_invitation.revoke(now)
                await self._uow.invitations.save(current_invitation)

            new_invitation_id = InvitationId.new()

            issued_token = self._invitation_token_issuer.issue(
                invitation_id=new_invitation_id,
                invited_by=inviter_id,
                employee_email=invited_email,
                issued_at=now,
            )

            new_invitation = Invitation.issue(
                invitation_id=new_invitation_id,
                invited_by=inviter.id,
                invited_email=invited_email,
                token_hash=issued_token.token_hash,
                roles=invited_employee.roles,
                created_at=now,
                expires_at=issued_token.expires_at,
            )

            await self._uow.invitations.add(new_invitation)
            await self._uow.commit()

        result = ReissueInvitationResult(
            invitation_id=new_invitation.id.value,
            inviter_id=inviter_id.value,
            employee_id=invited_employee.id.value,
        )

        try:
          await self._email_sender.send(
              email=invited_email,
              plain_token=issued_token.plain_token,
          )
        except EmailDeliveryError as error:
          raise InvitationDeliveryError(
              invitation_id=result.invitation_id
          ) from error

        return result
