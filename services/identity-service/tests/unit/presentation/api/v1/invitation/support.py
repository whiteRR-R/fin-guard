from uuid import UUID

from identity.domain.enums.role import EmployeeRole
from identity.infrastructure.persistence.models.employee import EmployeeModel
from identity.infrastructure.persistence.models.invitation import InvitationModel
from tests.unit.presentation.api.v1.support import FakeSession


class InvitationSession(FakeSession):
    def __init__(self, roles: list[EmployeeRole]) -> None:
        super().__init__(roles)
        self.invited_employee: EmployeeModel | None = None
        self.invitations: list[InvitationModel] = []

    async def scalar(self, statement):
        model = statement.column_descriptions[0]["entity"]
        values = tuple(statement.compile().params.values())

        if model is EmployeeModel:
            for value in values:
                if isinstance(value, UUID):
                    if value == self.employee.id:
                        return self.employee
                    if self.invited_employee and value == self.invited_employee.id:
                        return self.invited_employee
                    return None
                if isinstance(value, str) and "@" in value:
                    if value == self.employee.email:
                        return self.employee
                    if self.invited_employee and value == self.invited_employee.email:
                        return self.invited_employee
                    return None

        if model is InvitationModel:
            for value in values:
                if isinstance(value, UUID):
                    return next(
                        (item for item in self.invitations if item.id == value), None
                    )
                if isinstance(value, str) and "@" in value:
                    return next(
                        (
                            item
                            for item in reversed(self.invitations)
                            if item.invited_email == value
                        ),
                        None,
                    )

        return await super().scalar(statement)

    def add(self, value: object) -> None:
        super().add(value)
        if isinstance(value, EmployeeModel):
            self.invited_employee = value
        elif isinstance(value, InvitationModel):
            self.invitations.append(value)
