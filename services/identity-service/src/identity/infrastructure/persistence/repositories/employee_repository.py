from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.value_objects.employee_id import EmployeeId
from identity.infrastructure.persistence.models.employee import EmployeeModel
from identity.infrastructure.persistence.data_mapper.employee_mapper import (
    EmployeeMapper,
)


class EmployeeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _load_one(self, statement: Select[tuple[EmployeeModel]]):
        model = await self._session.scalars(statement)

    async def add(self, employee: EmployeeAccount):
        employee_model = EmployeeMapper.to_model(employee)
        self._session.add(employee_model)

    async def save(self, employee: EmployeeAccount, model: EmployeeModel):
        statement = (
            select(EmployeeModel)
            .where(EmployeeModel.id == employee.id.value)
            .with_for_update()
        )

        

        if model is None:
            raise LookupError("Employee not found")

        EmployeeMapper.update_model(employee, model)

    async def get_by_id(self, employee_id: EmployeeId) -> EmployeeAccount | None:
        statement = select(EmployeeModel).where(EmployeeModel.id == employee_id.value)
        result = await self._session.execute(statement)

        employee = result.scalar_one_or_none()

        if employee:
            return EmployeeMapper.to_domain(employee)

        return None

    async def get_by_email(self, employee_email: EmployeeId) -> EmployeeAccount | None:
        stmt = select(EmployeeModel).where(EmployeeModel.email == employee_email.value)
        result = await self._session.execute(stmt)

        employee = result.scalar_one_or_none()

        if employee:
            return EmployeeMapper.to_domain(employee)

        return None
