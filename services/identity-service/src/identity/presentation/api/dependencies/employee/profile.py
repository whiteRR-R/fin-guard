from identity.application.commands.change_email.handler import ChangeEmailHandler
from identity.application.commands.change_password.handler import ChangePasswordHandler
from identity.application.queries.get_current_employee.handler import (
    GetCurrentEmployeeHandler,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.presentation.api.dependencies.repositories import (
    AsyncSessionDependency,
    EmployeeRepositoryDependency,
    RefreshSessionRepositoryDependency,
)
from identity.presentation.api.dependencies.services import (
    ClockDependency,
    PasswordHasherDependency,
)


async def get_current_employee_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
) -> GetCurrentEmployeeHandler:
    return GetCurrentEmployeeHandler(
        uow=SqlAlchemyUnitOfWork(session),
        employee_repository=employees,
    )


async def get_change_email_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    password_hasher: PasswordHasherDependency,
) -> ChangeEmailHandler:
    return ChangeEmailHandler(
        uow=SqlAlchemyUnitOfWork(session),
        employees=employees,
        password_hasher=password_hasher,
    )


async def get_change_password_handler(
    session: AsyncSessionDependency,
    employees: EmployeeRepositoryDependency,
    refresh_sessions: RefreshSessionRepositoryDependency,
    clock: ClockDependency,
    password_hasher: PasswordHasherDependency,
) -> ChangePasswordHandler:
    return ChangePasswordHandler(
        uow=SqlAlchemyUnitOfWork(session),
        employees=employees,
        refresh_sessions=refresh_sessions,
        clock=clock,
        password_hasher=password_hasher,
    )
