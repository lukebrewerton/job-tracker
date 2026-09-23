# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_public_base_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    with pytest.raises(ValidationError, match="public_base_url"):
        Settings(_env_file=None)


def test_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://Jobs.Example.test")
    s = Settings(_env_file=None)
    assert s.public_host == "jobs.example.test"
