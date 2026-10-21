from sqlalchemy import any_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.infrastructure.persistence.data_mapper.employee_mapper import (
    EmployeeMapper,
)
from identity.infrastructure.persistence.models.employee import EmployeeModel


class EmployeeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_admin(self) -> bool:
        statement = (
            select(EmployeeModel.id)
            .where(any_(EmployeeModel.roles) == EmployeeRole.ADMIN)
            .limit(1)
        )
        return await self._session.scalar(statement) is not None

    async def lock_role_changes(self) -> None:
        await self._session.execute(text("SELECT pg_advisory_xact_lock(631992472001)"))

    async def count_active_admins(self) -> int:
        statement = select(func.count(EmployeeModel.id)).where(
            EmployeeModel.status == EmployeeStatus.ACTIVE,
            any_(EmployeeModel.roles) == EmployeeRole.ADMIN,
        )
        return int(await self._session.scalar(statement) or 0)

    async def get_by_id_with_lock(
        self, employee_id: EmployeeId
    ) -> EmployeeAccount | None:
        statement = (
            select(EmployeeModel)
            .where(EmployeeModel.id == employee_id.value)
            .with_for_update()
        )
        return self._to_domain_or_none(await self._session.scalar(statement))

    async def get_by_id(self, employee_id: EmployeeId) -> EmployeeAccount | None:
        statement = select(EmployeeModel).where(EmployeeModel.id == employee_id.value)
        return self._to_domain_or_none(await self._session.scalar(statement))

    async def get_by_email(self, email: Email) -> EmployeeAccount | None:
        statement = select(EmployeeModel).where(
            func.lower(EmployeeModel.email) == email.value
        )
        return self._to_domain_or_none(await self._session.scalar(statement))

    async def get_by_email_with_lock(self, email: Email) -> EmployeeAccount | None:
        statement = (
            select(EmployeeModel)
            .where(func.lower(EmployeeModel.email) == email.value)
            .with_for_update()
        )
        return self._to_domain_or_none(await self._session.scalar(statement))

    async def list_page(self, *, limit: int, offset: int) -> list[EmployeeAccount]:
        statement = (
            select(EmployeeModel).order_by(EmployeeModel.id).limit(limit).offset(offset)
        )
        return [
            EmployeeMapper.to_domain(model)
            for model in await self._session.scalars(statement)
        ]

    async def add(self, employee: EmployeeAccount) -> None:
        self._session.add(EmployeeMapper.to_model(employee))

    async def save(self, employee: EmployeeAccount) -> None:
        statement = (
            select(EmployeeModel)
            .where(EmployeeModel.id == employee.id.value)
            .with_for_update()
        )
        model = await self._session.scalar(statement)
        if model is None:
            raise LookupError("Employee not found")
        EmployeeMapper.update_model(employee, model)

    @staticmethod
    def _to_domain_or_none(model: EmployeeModel | None) -> EmployeeAccount | None:
        return EmployeeMapper.to_domain(model) if model is not None else None
