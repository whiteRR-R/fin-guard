from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, EmailStr, Field, SecretStr, model_validator
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


class MailSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    smtp_host: str = Field(default=..., min_length=1)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    smtp_from_email: EmailStr = Field(default=...)
    smtp_timeout_seconds: float = Field(default=10, gt=0)
    invitation_accept_url: AnyHttpUrl = Field(default=...)

    @model_validator(mode="after")
    def credentials_are_paired(self) -> "MailSettings":
        if (self.smtp_username is None) != (self.smtp_password is None):
            raise ValueError("SMTP username and password must be set together")
        if self.smtp_username is not None and self.smtp_password is not None:
            if not self.smtp_username or not self.smtp_password.get_secret_value():
                raise ValueError("SMTP credentials must not be empty")
            if self.smtp_security == "none":
                raise ValueError("SMTP authentication requires TLS")
        if (
            self.invitation_accept_url.scheme != "https"
            and self.invitation_accept_url.host not in {"localhost", "127.0.0.1"}
        ):
            raise ValueError("Invitation acceptance URL must use HTTPS")
        return self


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
