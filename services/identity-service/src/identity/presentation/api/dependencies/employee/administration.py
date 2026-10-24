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
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import (
    AsyncSessionDependency,
    EmployeeRepositoryDependency,
    OutboxRepositoryDependency,
    RefreshSessionRepositoryDependency,
)
from identity.presentation.api.dependencies.services import ClockDependency


async def get_list_employees_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
) -> ListEmployeesHandler:
    return ListEmployeesHandler(
        uow=SqlAlchemyUnitOfWork(session),
        employee_repository=employees,
    )


async def get_employee_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
) -> GetEmployeeHandler:
    return GetEmployeeHandler(
        uow=SqlAlchemyUnitOfWork(session),
        employee_repository=employees,
    )


async def get_block_employee_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    refresh_sessions: RefreshSessionRepositoryDependency,
    clock: ClockDependency,
) -> BlockEmployeeHandler:
    return BlockEmployeeHandler(
        uow=SqlAlchemyUnitOfWork(session),
        employees=employees,
        refresh_sessions=refresh_sessions,
        clock=clock,
        block_policy=EmployeeBlockPolicy(),
    )


async def get_unblock_employee_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
) -> UnblockEmployeeHandler:
    return UnblockEmployeeHandler(
        uow=SqlAlchemyUnitOfWork(session),
        employees=employees,
        unblock_policy=EmployeeUnblockPolicy(),
    )


async def get_assign_role_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    outbox: OutboxRepositoryDependency,
    clock: ClockDependency,
) -> AssignRoleHandler:
    return AssignRoleHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        employees=employees,
        outbox=outbox,
    )


async def get_revoke_role_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    outbox: OutboxRepositoryDependency,
    clock: ClockDependency,
) -> RevokeRoleHandler:
    return RevokeRoleHandler(
        uow=SqlAlchemyUnitOfWork(session),
        clock=clock,
        employees=employees,
        outbox=outbox,
    )
