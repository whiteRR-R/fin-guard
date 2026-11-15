from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.aggregates.service_account import ServiceAccount
from identity.domain.value_objects.service_account import ClientId, ServiceAccountId
from identity.infrastructure.persistence.data_mapper.service_account_mapper import (
    ServiceAccountMapper,
)
from identity.infrastructure.persistence.models.service_account import (
    ServiceAccountModel,
)


class ServiceAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, service_account_id: ServiceAccountId
    ) -> ServiceAccount | None:
        statement = select(ServiceAccountModel).where(
            ServiceAccountModel.id == service_account_id.value
        )
        return self._to_domain_or_none(await self._session.scalar(statement))

    async def get_by_id_with_lock(
        self, service_account_id: ServiceAccountId
    ) -> ServiceAccount | None:
        statement = (
            select(ServiceAccountModel)
            .where(ServiceAccountModel.id == service_account_id.value)
            .with_for_update()
        )
        return self._to_domain_or_none(await self._session.scalar(statement))

    async def get_by_client_id(self, client_id: ClientId) -> ServiceAccount | None:
        statement = select(ServiceAccountModel).where(
            ServiceAccountModel.client_id == client_id.value
        )
        return self._to_domain_or_none(await self._session.scalar(statement))

    async def list_page(self, *, limit: int, offset: int) -> list[ServiceAccount]:
        statement = (
            select(ServiceAccountModel)
            .order_by(ServiceAccountModel.created_at, ServiceAccountModel.id)
            .limit(limit)
            .offset(offset)
        )
        models = await self._session.scalars(statement)
        return [ServiceAccountMapper.to_domain(model) for model in models]

    async def add(self, service_account: ServiceAccount) -> None:
        self._session.add(ServiceAccountMapper.to_model(service_account))

    async def save(self, service_account: ServiceAccount) -> None:
        statement = (
            select(ServiceAccountModel)
            .where(ServiceAccountModel.id == service_account.id.value)
            .with_for_update()
        )
        model = await self._session.scalar(statement)

        if model is None:
            raise LookupError("Service account not found")

        ServiceAccountMapper.update_model(service_account, model)

    async def save_last_used_at(self, service_account: ServiceAccount) -> None:
        last_used_at = service_account.last_used_at
        if last_used_at is None:
            return

        await self._session.execute(
            update(ServiceAccountModel)
            .where(
                ServiceAccountModel.id == service_account.id.value,
                or_(
                    ServiceAccountModel.last_used_at.is_(None),
                    ServiceAccountModel.last_used_at < last_used_at,
                ),
            )
            .values(last_used_at=last_used_at)
        )

    @staticmethod
    def _to_domain_or_none(model: ServiceAccountModel | None) -> ServiceAccount | None:
        return ServiceAccountMapper.to_domain(model) if model is not None else None
