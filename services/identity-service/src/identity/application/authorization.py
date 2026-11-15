from identity.application.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    EmployeeNotActiveError,
)
from identity.application.ports.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.value_objects.employee_id import EmployeeId


async def require_active_admin(
    employees: EmployeeRepository,
    actor_id: EmployeeId,
    *,
    action: str,
) -> EmployeeAccount:
    actor = await employees.get_by_id(actor_id)

    if actor is None:
        raise AuthenticationError("Invalid actor")

    if actor.status is not EmployeeStatus.ACTIVE:
        raise EmployeeNotActiveError("Actor must be active")

    if EmployeeRole.ADMIN not in actor.roles:
        raise AccessDeniedError(f"Only an administrator can {action}")

    return actor
