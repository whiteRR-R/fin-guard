from identity.application.commands.accept_invitation.command import (
    AcceptInvitationCommand,
)
from identity.application.exceptions import (
    EmployeeNotFoundError,
    InvitationNotFoundError,
)
from identity.application.ports.clock import Clock
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.application.ports.repositories.invitation_repository import (
    InvitationRepository,
)
from identity.application.ports.security.invitation_token_verifier import (
    InvitationTokenVerifier,
)
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.application.ports.unit_of_work import UnitOfWork
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.password import Password


class AcceptInvitationHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        employees: EmployeeRepository,
        invitations: InvitationRepository,
        password_hasher: PasswordHasher,
        invitation_verifier: InvitationTokenVerifier,
    ) -> None:

        self._uow = uow
        self._clock = clock
        self._employees = employees
        self._invitations = invitations
        self._password_hasher = password_hasher
        self._invitation_verifier = invitation_verifier

    async def execute(self, command: AcceptInvitationCommand):
        claims = self._invitation_verifier.verify(command.token)

        invitation_id = InvitationId(claims.invitation_id)
        password = Password(command.password)

        async with self._uow:
            existing_invitation = await self._invitations.get_by_id(invitation_id)

            if existing_invitation is None:
                raise InvitationNotFoundError("Invitation not found")

            existing_employee = await self._employees.get_by_email(
                existing_invitation.invited_email
            )

            if existing_employee is None:
                raise EmployeeNotFoundError("Employee not found")

            now = self._clock.now()
            hashed_password = self._password_hasher.hash(password)

            existing_invitation.accept(now)
            existing_employee.activate(hashed_password)

            await self._invitations.save(existing_invitation)
            await self._employees.save(existing_employee)

            await self._uow.commit()
