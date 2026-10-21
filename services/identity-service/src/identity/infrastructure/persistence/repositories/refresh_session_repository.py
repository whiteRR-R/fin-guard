from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.aggregates.refresh_session import RefreshSession
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.refresh_session import (
    RefreshSessionId,
    RefreshTokenHash,
)
from identity.infrastructure.persistence.data_mapper.refresh_session_mapper import (
    RefreshSessionMapper,
)
from identity.infrastructure.persistence.models.session import SessionModel
from identity.infrastructure.persistence.models.used_refresh_token import (
    UsedRefreshTokenModel,
)


class RefreshSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id_with_lock(
        self, session_id: RefreshSessionId
    ) -> RefreshSession | None:
        statement = (
            select(SessionModel)
            .where(SessionModel.id == session_id.value)
            .with_for_update()
        )

        return self._to_domain_or_none(await self._session.scalar(statement))

    async def list_used_refresh_token_hashes(
        self, session_id: RefreshSessionId
    ) -> tuple[RefreshTokenHash, ...]:
        statement = (
            select(UsedRefreshTokenModel.token_hash)
            .where(UsedRefreshTokenModel.session_id == session_id.value)
            .order_by(UsedRefreshTokenModel.used_at, UsedRefreshTokenModel.token_hash)
        )
        hashes = await self._session.scalars(statement)

        return tuple(RefreshTokenHash(value) for value in hashes)

    async def add_used_refresh_token_hash(
        self, session_id: RefreshSessionId, token_hash: RefreshTokenHash
    ) -> None:
        self._session.add(
            UsedRefreshTokenModel(
                session_id=session_id.value,
                token_hash=token_hash.value,
            )
        )

    async def get_by_id(self, session_id: RefreshSessionId) -> RefreshSession | None:
        statement = select(SessionModel).where(SessionModel.id == session_id.value)
        return self._to_domain_or_none(await self._session.scalar(statement))

    async def list_active_by_employee(
        self, employee_id: EmployeeId
    ) -> list[RefreshSession]:
        statement = self._active_by_employee_statement(employee_id)
        models = await self._session.scalars(statement)

        return [RefreshSessionMapper.to_domain(model) for model in models]

    async def list_active_by_employee_with_lock(
        self, employee_id: EmployeeId, *, active_at: datetime
    ) -> list[RefreshSession]:
        statement = self._active_by_employee_statement(employee_id, active_at=active_at)
        models = await self._session.scalars(statement.with_for_update())

        return [RefreshSessionMapper.to_domain(model) for model in models]

    @staticmethod
    def _active_by_employee_statement(
        employee_id: EmployeeId, *, active_at: datetime | None = None
    ) -> Select[tuple[SessionModel]]:
        point_in_time = active_at if active_at is not None else func.now()

        return (
            select(SessionModel)
            .where(
                SessionModel.employee_id == employee_id.value,
                SessionModel.revoked_at.is_(None),
                SessionModel.created_at <= point_in_time,
                SessionModel.expires_at > point_in_time,
            )
            .order_by(SessionModel.created_at.desc(), SessionModel.id)
        )

    async def add(self, refresh_session: RefreshSession) -> None:
        self._session.add(RefreshSessionMapper.to_model(refresh_session))

    async def save(self, refresh_session: RefreshSession) -> None:
        statement = (
            select(SessionModel)
            .where(SessionModel.id == refresh_session.id.value)
            .with_for_update()
        )
        model = await self._session.scalar(statement)

        if model is None:
            raise LookupError("Refresh session not found")

        RefreshSessionMapper.update_model(refresh_session, model)

    @staticmethod
    def _to_domain_or_none(model: SessionModel | None) -> RefreshSession | None:
        return RefreshSessionMapper.to_domain(model) if model is not None else None
