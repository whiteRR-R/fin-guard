from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.exceptions import EmployeeDeletionNotAllowedError


class EmployeeDeletionPolicy:
    def ensure_allowed(
        self,
        *,
        actor: EmployeeAccount,
        target: EmployeeAccount,
    ) -> None:
        if actor.status is not EmployeeStatus.ACTIVE:
            raise EmployeeDeletionNotAllowedError(
                "Inactive employee cannot delete employees"
            )

        if EmployeeRole.ADMIN not in actor.roles:
            raise EmployeeDeletionNotAllowedError(
                "Only administrators can delete employees"
            )

        if actor.id == target.id:
            raise EmployeeDeletionNotAllowedError(
                "Administrator cannot delete itself"
            )

        if EmployeeRole.ADMIN in target.roles:
            raise EmployeeDeletionNotAllowedError(
                "Administrator cannot delete another administrator"
            )
