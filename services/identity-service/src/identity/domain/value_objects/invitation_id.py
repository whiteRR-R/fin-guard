from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class InvitationId:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("InvitationId value must be UUID")

    @classmethod
    def new(cls) -> "InvitationId":
        return cls(uuid4())
