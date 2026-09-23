# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any

import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED_ENV = {
    "PUBLIC_BASE_URL": "https://jobs.example.test",
    "DATABASE_URL": "postgresql://u:p@db.example.test/jt",
    "OIDC_CLIENT_ID": "client-id",
    "OIDC_CLIENT_SECRET": "client-secret",
    "SESSION_SECRET": "s" * 32,
    "ALLOWED_EMAILS": "me@example.test",
}


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {k.lower(): v for k, v in REQUIRED_ENV.items()}
    values.update(overrides)
    return Settings(**values, _env_file=None)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (*REQUIRED_ENV, "OIDC_ISSUER"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize("missing", list(REQUIRED_ENV))
def test_required_settings(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    for var, value in REQUIRED_ENV.items():
        if var != missing:
            monkeypatch.setenv(var, value)
    with pytest.raises(ValidationError, match=missing.lower()):
        Settings(_env_file=None)


def test_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for var, value in REQUIRED_ENV.items():
        monkeypatch.setenv(var, value)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://Jobs.Example.test")
    s = Settings(_env_file=None)
    assert s.public_host == "jobs.example.test"
    assert str(s.oidc_issuer) == "https://accounts.google.com/"  # default: Google


@pytest.mark.parametrize(
    "given",
    ["postgresql://u:p@db.example.test/jt", "postgresql+psycopg://u:p@db.example.test/jt"],
)
def test_database_url_uses_psycopg_driver(given: str) -> None:
    s = _settings(database_url=given)
    assert s.database_url.get_secret_value() == "postgresql+psycopg://u:p@db.example.test/jt"


@pytest.mark.parametrize("given", ["mysql://u:p@h/db", "postgresql+asyncpg://u:p@h/db", "nonsense"])
def test_database_url_rejects_other_drivers(given: str) -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL must start with"):
        _settings(database_url=given)


def test_secrets_not_in_repr() -> None:
    s = _settings(
        database_url="postgresql://u:s3cret-pw@db.example.test/jt",
        oidc_client_secret="oidc-s3cret",
        session_secret="session-s3cret-" + "x" * 32,
    )
    for secret in ("s3cret-pw", "oidc-s3cret", "session-s3cret"):
        assert secret not in repr(s)
        assert secret not in str(s.model_dump())


def test_session_secret_must_be_long_enough() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        _settings(session_secret="short")


def test_allowed_emails_are_trimmed_lowercased_and_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var, value in REQUIRED_ENV.items():
        monkeypatch.setenv(var, value)
    monkeypatch.setenv("ALLOWED_EMAILS", " Me@Example.test , other@example.test,,me@example.test ")
    s = Settings(_env_file=None)
    assert s.allowed_emails == frozenset({"me@example.test", "other@example.test"})


@pytest.mark.parametrize("given", ["", " , ,"])
def test_allowed_emails_cannot_be_empty(given: str) -> None:
    with pytest.raises(ValidationError, match="at least one email"):
        _settings(allowed_emails=given)


@pytest.mark.parametrize(
    ("url", "secure"), [("https://x.test", True), ("http://localhost:8000", False)]
)
def test_cookies_are_secure_on_https(url: str, secure: bool) -> None:
    assert _settings(public_base_url=url).secure_cookies is secure
