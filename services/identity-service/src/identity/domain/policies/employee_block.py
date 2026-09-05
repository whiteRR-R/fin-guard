from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.exceptions import EmployeeBlockNotAllowedError


class EmployeeBlockPolicy:
    def ensure_allowed(
        self,
        *,
        actor: EmployeeAccount,
        target: EmployeeAccount,
    ) -> None:
        if actor.status is not EmployeeStatus.ACTIVE:
            raise EmployeeBlockNotAllowedError(
                "Inactive employee cannot block employees"
            )

        if EmployeeRole.ADMIN not in actor.roles:
            raise EmployeeBlockNotAllowedError(
                "Only administrator can block employees"
            )

        if actor.id == target.id:
            raise EmployeeBlockNotAllowedError(
                "Administrator cannot block itself"
            )

        if EmployeeRole.ADMIN in target.roles:
            raise EmployeeBlockNotAllowedError(
                "Administrator cannot block another administrator"
            )
