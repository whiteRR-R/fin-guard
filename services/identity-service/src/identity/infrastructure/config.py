from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_url: SecretStr = Field(default=..., repr=False)


class TokenSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    access_token_signing_key: SecretStr = Field(default=..., repr=False)
    refresh_token_signing_key: SecretStr = Field(default=..., repr=False)
    invitation_signing_key: SecretStr = Field(default=..., repr=False)
    token_issuer: str = Field(default=..., min_length=1)
    token_audience: str = Field(default=..., min_length=1)
    access_token_lifetime_seconds: int = Field(default=900, gt=0)
    refresh_token_lifetime_days: int = Field(default=30, gt=0)
    invitation_token_lifetime_days: int = Field(default=7, gt=0)


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
