"""Application settings. Every value comes from the environment (guide 16.1)."""

import base64
import binascii
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The placeholder shipped in .env.example. Starting with it must fail (guide 12.7).
PLACEHOLDER_SECRET_KEY = "change-me-to-64-random-chars"  # noqa: S105 - rejected below, never used
MIN_SECRET_KEY_BYTES = 32
ENCRYPTION_KEY_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    winnow_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    secret_key: SecretStr
    encryption_key: SecretStr

    database_url: str = "postgresql+asyncpg://winnow:winnow@db:5432/winnow"
    redis_url: str = "redis://redis:6379/0"
    public_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8080")

    winnow_single_user: bool = False
    registration: Literal["open", "invite_only", "closed"] = "open"

    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint: AnyHttpUrl | None = None
    s3_bucket: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None

    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "Winnow <no-reply@example.com>"

    clamav_host: str = "clamav"
    unpaywall_email: str | None = None

    llm_provider: Literal["none", "anthropic", "openai_compatible"] = "none"
    llm_api_key: SecretStr | None = None
    llm_base_url: AnyHttpUrl | None = None
    llm_model: str | None = None

    max_upload_mb: int = Field(default=200, ge=1, le=10_000)
    session_idle_days: int = Field(default=7, ge=1, le=365)

    @field_validator("secret_key")
    @classmethod
    def _secret_key_is_strong(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if secret == PLACEHOLDER_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is still the .env.example placeholder; generate a real one"
            )
        if len(secret.encode()) < MIN_SECRET_KEY_BYTES:
            raise ValueError(f"SECRET_KEY must be at least {MIN_SECRET_KEY_BYTES} bytes")
        return value

    @field_validator("encryption_key")
    @classmethod
    def _encryption_key_is_32_bytes(cls, value: SecretStr) -> SecretStr:
        try:
            raw = base64.b64decode(value.get_secret_value(), validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("ENCRYPTION_KEY must be base64 (openssl rand -base64 32)") from None
        if len(raw) != ENCRYPTION_KEY_BYTES:
            raise ValueError(f"ENCRYPTION_KEY must decode to exactly {ENCRYPTION_KEY_BYTES} bytes")
        return value

    @field_validator("database_url")
    @classmethod
    def _database_url_is_async_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return value

    @field_validator("redis_url")
    @classmethod
    def _redis_url_scheme(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must use the redis:// or rediss:// scheme")
        return value

    @model_validator(mode="after")
    def _production_uses_https(self) -> "Settings":
        if self.is_production and self.public_url.scheme != "https":
            raise ValueError("PUBLIC_URL must be https in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.winnow_env == "production"

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are served in development only (guide 10)."""
        return not self.is_production

    @property
    def encryption_key_bytes(self) -> bytes:
        return base64.b64decode(self.encryption_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    """Settings for the running process, read from the environment once."""
    return Settings()
