from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class EmployeeId:
    value: UUID

    @classmethod
    def new(cls) -> "EmployeeId":
        return cls(uuid4())
