from identity.application.authentication.authenticate_access_token import CurrentActor
from identity.presentation.api.dependencies.repositories import RepositoryDependencies
from identity.presentation.api.dependencies.types import Provider
from identity.presentation.api.dependencies.invitation.acceptance import (
    create_invitation_acceptance_dependencies,
)
from identity.presentation.api.dependencies.invitation.administration import (
    create_invitation_administration_dependencies,
)
from identity.presentation.api.dependencies.invitation.types import (
    InvitationApiServices,
    InvitationDependencies,
)


def create_invitation_dependencies(
    services: InvitationApiServices,
    repositories: RepositoryDependencies,
    actor: Provider[CurrentActor],
) -> InvitationDependencies:
    administration = create_invitation_administration_dependencies(services, repositories)
    acceptance = create_invitation_acceptance_dependencies(services, repositories)
    return InvitationDependencies(
        actor=actor,
        invite=administration.invite,
        accept=acceptance.accept,
        revoke=administration.revoke,
        reissue=administration.reissue,
    )
