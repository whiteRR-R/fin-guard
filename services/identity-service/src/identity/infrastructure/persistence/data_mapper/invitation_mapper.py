from identity.domain.aggregates.invitation import Invitation
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.invitation_id import InvitationId
from identity.domain.value_objects.invitation_token_hash import InvitationTokenHash
from identity.infrastructure.persistence.models.invitation import InvitationModel


class InvitationMapper:
    @staticmethod
    def to_domain(model: InvitationModel) -> Invitation:
        return Invitation.restore(
            invitation_id=InvitationId(model.id),
            invited_by=EmployeeId(model.invited_by),
            invited_email=Email(model.invited_email),
            roles=model.roles,
            status=model.status,
            token_hash=InvitationTokenHash(model.token_hash),
            created_at=model.created_at,
            expires_at=model.expires_at,
            accepted_at=model.accepted_at,
            revoked_at=model.revoked_at,
        )

    @staticmethod
    def to_model(invitation: Invitation) -> InvitationModel:
        return InvitationModel(
            id=invitation.id.value,
            invited_by=invitation.invited_by.value,
            invited_email=invitation.invited_email.value,
            roles=sorted(invitation.roles, key=lambda role: role.value),
            status=invitation.status,
            token_hash=invitation.token_hash.value,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
            revoked_at=invitation.revoked_at,
        )

    @staticmethod
    def update_model(invitation: Invitation, model: InvitationModel) -> None:
        if model.id != invitation.id.value:
            raise ValueError("Invitation ID does not match model ID")
        model.invited_by = invitation.invited_by.value
        model.invited_email = invitation.invited_email.value
        model.roles = sorted(invitation.roles, key=lambda role: role.value)
        model.status = invitation.status
        model.token_hash = invitation.token_hash.value
        model.created_at = invitation.created_at
        model.expires_at = invitation.expires_at
        model.accepted_at = invitation.accepted_at
        model.revoked_at = invitation.revoked_at
