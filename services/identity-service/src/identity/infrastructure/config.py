from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_url: SecretStr = Field(repr=False)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            database_url = make_url(value.get_secret_value())
            database_url.port
        except (ArgumentError, ValueError):
            raise ValueError("DATABASE_URL is invalid") from None

        if database_url.drivername != "postgresql+asyncpg":
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver")
        if not database_url.database:
            raise ValueError("DATABASE_URL must include a database name")

        return value

    @property
    def sqlalchemy_url(self) -> URL:
        return make_url(self.database_url.get_secret_value())
