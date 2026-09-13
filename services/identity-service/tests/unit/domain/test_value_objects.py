import pytest

from identity.domain.exceptions import (
    EmailValidationError,
    PasswordValidationError,
)
from identity.domain.value_objects.email import Email
from identity.domain.value_objects.password import Password


def test_email_is_normalized() -> None:
    email = Email("  USER@example.com  ")

    assert email.value == "user@example.com"


def test_invalid_email_is_rejected() -> None:
    with pytest.raises(EmailValidationError):
        Email("not-an-email")


def test_password_with_12_characters_is_valid() -> None:
    password = Password("abcdefghijkl")

    assert password.value == "abcdefghijkl"


def test_short_password_is_rejected() -> None:
    with pytest.raises(PasswordValidationError):
        Password("short")


def test_password_longer_than_72_bytes_is_rejected() -> None:
    with pytest.raises(PasswordValidationError):
        Password("я" * 37)
