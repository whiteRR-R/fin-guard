import bcrypt

from identity.domain.value_objects.password import HashedPassword, Password


class BcryptPasswordHasher:
    def hash(self, password: Password) -> HashedPassword:
        password_hash = bcrypt.hashpw(
            password.value.encode("utf-8"),
            bcrypt.gensalt(),
        )
        return HashedPassword(password_hash.decode("ascii"))

    def verify(self, password: Password, hashed_password: HashedPassword) -> bool:
        try:
            return bcrypt.checkpw(
                password.value.encode("utf-8"),
                hashed_password.value.encode("ascii"),
            )
        except (UnicodeEncodeError, ValueError):
            return False
