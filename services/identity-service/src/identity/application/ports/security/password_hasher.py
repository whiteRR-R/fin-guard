from typing import Protocol

from identity.domain.value_objects.password import HashedPassword, Password


class PasswordHasher(Protocol):
    def hash(self, password: Password) -> HashedPassword: ...

    def verify(self, password: Password, hashed_password: HashedPassword) -> bool: ...
