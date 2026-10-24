from dataclasses import dataclass

from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.application.commands.accept_invitation.handler import (
    AcceptInvitationHandler,
)
from identity.application.commands.invite_employee.handler import InviteEmployeeHandler
from identity.application.commands.reissue_invitation.handler import (
    ReissueInvitationHandler,
)
from identity.application.commands.revoke_invitation.handler import (
    RevokeInvitationHandler,
)
from identity.application.ports.clock import Clock
from identity.application.ports.security.invitation_token_issuer import (
    InvitationTokenIssuer,
)
from identity.application.ports.security.invitation_token_verifier import (
    InvitationTokenVerifier,
)
from identity.application.ports.security.password_hasher import PasswordHasher
from identity.presentation.api.dependencies.types import Provider


@dataclass(frozen=True)
class InvitationApiServices:
    clock: Clock
    password_hasher: PasswordHasher
    token_issuer: InvitationTokenIssuer
    token_verifier: InvitationTokenVerifier


@dataclass(frozen=True)
class InvitationDependencies:
    actor: Provider[CurrentActor]
    invite: Provider[InviteEmployeeHandler]
    accept: Provider[AcceptInvitationHandler]
    revoke: Provider[RevokeInvitationHandler]
    reissue: Provider[ReissueInvitationHandler]
