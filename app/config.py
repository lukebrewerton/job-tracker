# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application settings, read from environment variables (and `.env` in development)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    @property
    def public_host(self) -> str:
        host = self.public_base_url.host
        assert host is not None  # AnyHttpUrl always has a host
        return host


@lru_cache
def get_settings() -> Settings:
    return Settings()
