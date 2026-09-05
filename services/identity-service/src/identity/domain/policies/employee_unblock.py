from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.exceptions import EmployeeUnblockNotAllowedError


class EmployeeUnblockPolicy:
    def ensure_allowed(
        self,
        *,
        actor: EmployeeAccount,
        target: EmployeeAccount,
    ) -> None:
        if actor.status is not EmployeeStatus.ACTIVE:
            raise EmployeeUnblockNotAllowedError(
                "Inactive employee cannot unblock employees"
            )

        if EmployeeRole.ADMIN not in actor.roles:
            raise EmployeeUnblockNotAllowedError(
                "Only administrator can unblock employees"
            )

        if actor.id == target.id:
            raise EmployeeUnblockNotAllowedError(
                "Administrator cannot unblock itself"
            )
