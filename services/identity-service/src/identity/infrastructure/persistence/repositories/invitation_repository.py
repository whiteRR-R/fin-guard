from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.aggregates.invitation import Invitation
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.invitation_id import InvitationId
from identity.infrastructure.persistence.data_mapper.invitation_mapper import (
    InvitationMapper,
)
from identity.infrastructure.persistence.models.invitation import InvitationModel


class InvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, invitation_id: InvitationId) -> Invitation | None:
        model = await self._session.get(InvitationModel, invitation_id.value)

        if model is None:
            return None

        return InvitationMapper.to_domain(model)

    async def get_by_id_with_lock(
        self, invitation_id: InvitationId
    ) -> Invitation | None:
        query = (
            select(InvitationModel)
            .where(InvitationModel.id == invitation_id.value)
            .with_for_update()
        )
        model = await self._session.scalar(query)

        if model is None:
            return None

        return InvitationMapper.to_domain(model)

    async def get_latest_by_employee_email(self, email: Email) -> Invitation | None:
        model = await self._session.scalar(self._latest_for_email(email))

        if model is None:
            return None

        return InvitationMapper.to_domain(model)

    async def get_latest_by_employee_email_with_lock(
        self, email: Email
    ) -> Invitation | None:
        await self._lock_email(email)

        model = await self._session.scalar(
            self._latest_for_email(email).with_for_update()
        )

        if model is None:
            return None

        return InvitationMapper.to_domain(model)

    async def add(self, invitation: Invitation) -> None:
        self._session.add(InvitationMapper.to_model(invitation))

    async def save(self, invitation: Invitation) -> None:
        query = (
            select(InvitationModel)
            .where(InvitationModel.id == invitation.id.value)
            .with_for_update()
        )
        model = await self._session.scalar(query)

        if model is None:
            raise LookupError("Invitation not found")

        InvitationMapper.update_model(invitation, model)

    @staticmethod
    def _latest_for_email(email: Email) -> Select[tuple[InvitationModel]]:
        return (
            select(InvitationModel)
            .where(func.lower(InvitationModel.invited_email) == email.value)
            .order_by(InvitationModel.created_at.desc(), InvitationModel.id.desc())
            .limit(1)
        )

    async def _lock_email(self, email: Email) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:email, 0))"),
            {"email": email.value},
        )
