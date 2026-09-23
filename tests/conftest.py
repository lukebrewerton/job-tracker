# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared fixtures: an app wired to a throwaway frontend build in a temp directory."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PUBLIC_BASE_URL = "https://job-tracker.example.test"


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """A minimal stand-in for Vite's dist/ output."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('app')")
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>")
    (tmp_path / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    return tmp_path


@pytest.fixture
def settings(static_dir: Path) -> Settings:
    return Settings(public_base_url=PUBLIC_BASE_URL, static_dir=static_dir)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url=PUBLIC_BASE_URL) as c:
        yield c
