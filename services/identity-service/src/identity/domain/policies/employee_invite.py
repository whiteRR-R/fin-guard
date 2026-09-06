from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.domain.exceptions import EmployeeInviteNotAllowedError


class EmployeeInvitePolicy:
    def ensure_allowed(self, actor: EmployeeAccount) -> None:

        if actor.status is not EmployeeStatus.ACTIVE:
            raise EmployeeInviteNotAllowedError("Only active actor can invite")

        if EmployeeRole.ADMIN not in actor.roles:
            raise EmployeeInviteNotAllowedError(
                "Only administrator can invite employee"
            )
