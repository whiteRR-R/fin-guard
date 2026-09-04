from dataclasses import dataclass, field

from identity.domain.exceptions import PasswordValidationError


@dataclass(frozen=True, slots=True)
class Password:
    value: str = field(repr=False)

    def __post_init__(self):
        if len(self.value) < 12:
            raise PasswordValidationError(
                "Password must contain at least 12 characters"
            )
        
        if len(self.value.encode("utf-8")) > 72:
            raise PasswordValidationError(
                "Password must not exceed 72 bytes"
            )


@dataclass(frozen=True, slots=True)
class HashedPassword:
    value: str = field(repr=False)

    def __post_init__(self):
        if not self.value:
            raise PasswordValidationError(
                "Password hash cannot be empty"
            )
