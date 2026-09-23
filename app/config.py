# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application settings, read from environment variables (and `.env` in development)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The canonical origin this instance is served on, e.g. https://job-tracker.example.com.
    # Requests arriving on any other host are redirected here. Required: no default.
    public_base_url: AnyHttpUrl

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Directory holding the built frontend (Vite's `dist/`). The Docker image sets this.
    static_dir: Path = Path("frontend/dist")

    @property
    def public_host(self) -> str:
        host = self.public_base_url.host
        assert host is not None  # AnyHttpUrl always has a host
        return host


@lru_cache
def get_settings() -> Settings:
    return Settings()
