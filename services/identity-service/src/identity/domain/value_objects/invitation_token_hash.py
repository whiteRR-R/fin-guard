from dataclasses import dataclass, field

from identity.domain.exceptions import InvitationTokenHashValidationError


@dataclass(frozen=True, slots=True)
class InvitationTokenHash:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvitationTokenHashValidationError(
                "Invitation token hash must be a string"
            )

        if not self.value.strip():
            raise InvitationTokenHashValidationError(
                "Invitation token hash cannot be empty"
            )
