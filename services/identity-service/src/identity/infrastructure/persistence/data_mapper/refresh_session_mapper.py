from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import RefreshSessionId, RefreshTokenHash
from identity.infrastructure.persistence.models.session import SessionModel


class RefreshSessionMapper:
    @staticmethod
    def to_domain(model: SessionModel) -> RefreshSession:
        return RefreshSession(
            session_id=RefreshSessionId(model.id),
            employee_id=EmployeeId(model.employee_id),
            refresh_token_hash=RefreshTokenHash(model.refresh_token_hash),
            created_at=model.created_at,
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
        )

    @staticmethod
    def to_model(session: RefreshSession) -> SessionModel:
        return SessionModel(
            id=session.id.value,
            employee_id=session.employee_id.value,
            refresh_token_hash=session.refresh_token_hash.value,
            created_at=session.created_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
        )

    @staticmethod
    def update_model(session: RefreshSession, model: SessionModel) -> None:
        if model.id != session.id.value:
            raise ValueError("Session ID does not match model ID")
        model.employee_id = session.employee_id.value
        model.refresh_token_hash = session.refresh_token_hash.value
        model.created_at = session.created_at
        model.expires_at = session.expires_at
        model.revoked_at = session.revoked_at
