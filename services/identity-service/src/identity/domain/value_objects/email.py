from dataclasses import dataclass

from email_validator import EmailNotValidError, validate_email

from identity.domain.exceptions import EmailValidationError


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        candidate = self.value.strip().lower()
        try:
            validated_email = validate_email(candidate, check_deliverability=False)
            object.__setattr__(self, "value", validated_email.normalized)
        except EmailNotValidError as e:
            raise EmailValidationError("Invalid email address") from e
