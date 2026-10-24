from identity.presentation.api.dependencies.employee.administration import (
    create_administration_dependencies,
)
from identity.presentation.api.dependencies.employee.authentication import (
    create_authentication_dependencies,
)
from identity.presentation.api.dependencies.employee.profile import (
    create_profile_dependencies,
)
from identity.presentation.api.dependencies.employee.types import (
    EmployeeApiServices,
    EmployeeDependencies,
)
from identity.presentation.api.dependencies.repositories import (
    RepositoryDependencies,
    create_repository_dependencies,
)


def create_employee_dependencies(
    services: EmployeeApiServices,
    repositories: RepositoryDependencies | None = None,
) -> EmployeeDependencies:
    if repositories is None:
        repositories = create_repository_dependencies(services.session_factory)
    authentication = create_authentication_dependencies(services, repositories)
    profile = create_profile_dependencies(services, repositories)
    administration = create_administration_dependencies(services, repositories)

    return EmployeeDependencies(
        actor=authentication.actor,
        login=authentication.login,
        current_employee=profile.current_employee,
        change_email=profile.change_email,
        change_password=profile.change_password,
        list_employees=administration.list_employees,
        get_employee=administration.get_employee,
        block_employee=administration.block_employee,
        unblock_employee=administration.unblock_employee,
        assign_role=administration.assign_role,
        revoke_role=administration.revoke_role,
    )
