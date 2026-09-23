# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PUBLIC_BASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize("missing", ["public_base_url", "database_url"])
def test_required_settings(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://jobs.example.test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.test/jt")
    monkeypatch.delenv(missing.upper())
    with pytest.raises(ValidationError, match=missing):
        Settings(_env_file=None)


def test_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://Jobs.Example.test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db.example.test/jt")
    s = Settings(_env_file=None)
    assert s.public_host == "jobs.example.test"


@pytest.mark.parametrize(
    "given",
    ["postgresql://u:p@db.example.test/jt", "postgresql+psycopg://u:p@db.example.test/jt"],
)
def test_database_url_uses_psycopg_driver(given: str) -> None:
    s = Settings(public_base_url="https://x.test", database_url=given, _env_file=None)
    assert s.database_url.get_secret_value() == "postgresql+psycopg://u:p@db.example.test/jt"


@pytest.mark.parametrize("given", ["mysql://u:p@h/db", "postgresql+asyncpg://u:p@h/db", "nonsense"])
def test_database_url_rejects_other_drivers(given: str) -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL must start with"):
        Settings(public_base_url="https://x.test", database_url=given, _env_file=None)


def test_database_password_not_in_repr() -> None:
    s = Settings(
        public_base_url="https://x.test",
        database_url="postgresql://u:s3cret-pw@db.example.test/jt",
        _env_file=None,
    )
    assert "s3cret-pw" not in repr(s)
    assert "s3cret-pw" not in str(s.model_dump())
