from identity.domain.aggregates.employee_account import EmployeeAccount
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.employee_id import EmployeeId
from identity.domain.value_objects.password import HashedPassword
from identity.infrastructure.persistence.models.employee import EmployeeModel


class EmployeeMapper:

    @staticmethod
    def to_domain(model: EmployeeModel) -> EmployeeAccount:
        password_hash = (
            HashedPassword(model.password_hash) if model.password_hash else None
        )

        return EmployeeAccount.restore(
            employee_id=EmployeeId(model.id),
            email=Email(model.email),
            password_hash=password_hash,
            roles=model.roles,
            status=model.status,
        )

    @staticmethod
    def to_model(employee: EmployeeAccount) -> EmployeeModel:

        password_hash = employee.password_hash

        return EmployeeModel(
            id=employee.id.value,
            email=employee.email.value,
            roles=sorted(employee.roles, key=lambda role: role.value),
            password_hash=password_hash.value if password_hash else None,
            status=employee.status,
        )

    @staticmethod
    def update_model(employee: EmployeeAccount, model: EmployeeModel) -> None:
        if model.id != employee.id.value:
            raise ValueError("Employee ID does not match model ID")

        password_hash = employee.password_hash

        model.email = employee.email.value
        model.roles = sorted(employee.roles, key=lambda role: role.value)
        model.password_hash = password_hash.value if password_hash else None
        model.status = employee.status
