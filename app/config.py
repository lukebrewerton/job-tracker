# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application settings, read from environment variables (and `.env` in development)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DRIVER_SCHEME = "postgresql+psycopg://"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The canonical origin this instance is served on, e.g. https://job-tracker.example.com.
    # Requests arriving on any other host are redirected here. Required: no default.
    public_base_url: AnyHttpUrl

    # Postgres connection string. Required. Plain `postgresql://` (as Neon's dashboard gives
    # it) is accepted and pointed at the psycopg 3 driver. SecretStr keeps the password out
    # of reprs and logs.
    database_url: SecretStr

    # --- Sign-in (OIDC) ---
    # The identity provider. Any OIDC issuer with discovery works; Google by default.
    oidc_issuer: AnyHttpUrl = AnyHttpUrl("https://accounts.google.com")
    oidc_client_id: str = Field(min_length=1)
    oidc_client_secret: SecretStr
    # Signs the short-lived cookie that carries state/nonce/next through the provider
    # round trip. Generate with: openssl rand -hex 32
    session_secret: SecretStr
    # Who may sign in: comma-separated, case-insensitive. Required and non-empty.
    allowed_emails: Annotated[frozenset[str], NoDecode]

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Directory holding the built frontend (Vite's `dist/`). The Docker image sets this.
    static_dir: Path = Path("frontend/dist")

    @field_validator("database_url", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, value: object) -> object:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw, str):
            return value
        if raw.startswith("postgresql://"):
            return _DRIVER_SCHEME + raw.removeprefix("postgresql://")
        if not raw.startswith(_DRIVER_SCHEME):
            raise ValueError("DATABASE_URL must start with postgresql:// or postgresql+psycopg://")
        return raw

    @field_validator("session_secret")
    @classmethod
    def _secret_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET must be at least 32 characters")
        return value

    @field_validator("allowed_emails", mode="before")
    @classmethod
    def _parse_allowed_emails(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.split(",")
        if isinstance(value, (list, tuple, set, frozenset)):
            emails = frozenset(str(e).strip().lower() for e in value if str(e).strip())
            if not emails:
                raise ValueError("ALLOWED_EMAILS must list at least one email address")
            return emails
        return value

    @property
    def secure_cookies(self) -> bool:
        """Cookies are Secure whenever the public origin is https."""
        return self.public_base_url.scheme == "https"

    @property
    def public_host(self) -> str:
        host = self.public_base_url.host
        assert host is not None  # AnyHttpUrl always has a host
        return host


@lru_cache
def get_settings() -> Settings:
    return Settings()
