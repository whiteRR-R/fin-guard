from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.commands.assign_role.handler import AssignRoleHandler
from identity.application.commands.block_employee.handler import BlockEmployeeHandler
from identity.application.commands.revoke_role.handler import RevokeRoleHandler
from identity.application.commands.unblock_employee.handler import (
    UnblockEmployeeHandler,
)
from identity.application.queries.get_employee.handler import GetEmployeeHandler
from identity.application.queries.list_employees.handler import ListEmployeesHandler
from identity.domain.policies.employee_block import EmployeeBlockPolicy
from identity.domain.policies.employee_unblock import EmployeeUnblockPolicy
from identity.infrastructure.persistence.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.infrastructure.persistence.repositories.outbox_repository import (
    OutboxRepository,
)
from identity.infrastructure.persistence.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.employee.repositories import (
    RepositoryDependencies,
)
from identity.presentation.api.dependencies.employee.types import (
    EmployeeApiServices,
    Provider,
)


@dataclass(frozen=True)
class AdministrationDependencies:
    list_employees: Provider[ListEmployeesHandler]
    get_employee: Provider[GetEmployeeHandler]
    block_employee: Provider[BlockEmployeeHandler]
    unblock_employee: Provider[UnblockEmployeeHandler]
    assign_role: Provider[AssignRoleHandler]
    revoke_role: Provider[RevokeRoleHandler]


def create_administration_dependencies(
    services: EmployeeApiServices,
    repositories: RepositoryDependencies,
) -> AdministrationDependencies:
    async def get_list_employees_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
    ) -> ListEmployeesHandler:
        return ListEmployeesHandler(
            uow=SqlAlchemyUnitOfWork(session),
            employee_repository=employees,
        )

    async def get_employee_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
    ) -> GetEmployeeHandler:
        return GetEmployeeHandler(
            uow=SqlAlchemyUnitOfWork(session),
            employee_repository=employees,
        )

    async def get_block_employee_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        refresh_sessions: Annotated[
            RefreshSessionRepository, Depends(repositories.refresh_sessions)
        ],
    ) -> BlockEmployeeHandler:
        return BlockEmployeeHandler(
            uow=SqlAlchemyUnitOfWork(session),
            employees=employees,
            refresh_sessions=refresh_sessions,
            clock=services.clock,
            block_policy=EmployeeBlockPolicy(),
        )

    async def get_unblock_employee_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
    ) -> UnblockEmployeeHandler:
        return UnblockEmployeeHandler(
            uow=SqlAlchemyUnitOfWork(session),
            employees=employees,
            unblock_policy=EmployeeUnblockPolicy(),
        )

    async def get_assign_role_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        outbox: Annotated[OutboxRepository, Depends(repositories.outbox)],
    ) -> AssignRoleHandler:
        return AssignRoleHandler(
            uow=SqlAlchemyUnitOfWork(session),
            clock=services.clock,
            employees=employees,
            outbox=outbox,
        )

    async def get_revoke_role_handler(
        session: Annotated[AsyncSession, Depends(repositories.session)],
        employees: Annotated[EmployeeRepository, Depends(repositories.employees)],
        outbox: Annotated[OutboxRepository, Depends(repositories.outbox)],
    ) -> RevokeRoleHandler:
        return RevokeRoleHandler(
            uow=SqlAlchemyUnitOfWork(session),
            clock=services.clock,
            employees=employees,
            outbox=outbox,
        )

    return AdministrationDependencies(
        list_employees=get_list_employees_handler,
        get_employee=get_employee_handler,
        block_employee=get_block_employee_handler,
        unblock_employee=get_unblock_employee_handler,
        assign_role=get_assign_role_handler,
        revoke_role=get_revoke_role_handler,
    )
