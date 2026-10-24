from identity.domain.value_objects.password import HashedPassword, Password
from identity.infrastructure.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)


def test_hash_can_be_verified_and_does_not_store_plain_password() -> None:
    hasher = BcryptPasswordHasher()
    password = Password("very-secret-password")

    password_hash = hasher.hash(password)

    assert password_hash.value.startswith("$2b$")
    assert password.value not in password_hash.value
    assert hasher.verify(password, password_hash)
    assert not hasher.verify(Password("another-secret-password"), password_hash)


def test_invalid_stored_hash_is_rejected() -> None:
    assert not BcryptPasswordHasher().verify(
        Password("very-secret-password"),
        HashedPassword("invalid-hash"),
    )
