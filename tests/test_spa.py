# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .conftest import PUBLIC_BASE_URL


@pytest.mark.parametrize("path", ["/", "/jobs", "/jobs/0190f1c2-7e4a/edit", "/interviews"])
def test_client_routes_get_index_html(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert "<div id=root>" in resp.text
    assert resp.headers["cache-control"] == "no-cache"


def test_assets_are_served(client: TestClient) -> None:
    resp = client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


def test_missing_asset_is_404_not_index(client: TestClient) -> None:
    assert client.get("/assets/missing.js").status_code == 404


def test_root_level_build_file_is_served(client: TestClient) -> None:
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.content == b"\x00\x00\x01\x00"


@pytest.mark.parametrize("path", ["/api", "/api/jobs", "/api/does/not/exist", "/auth/login"])
def test_reserved_prefixes_are_not_swallowed(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/json"


def test_apiary_is_not_a_reserved_prefix(client: TestClient) -> None:
    # Only the exact first segment `api` is reserved, not anything starting with it.
    assert client.get("/apiary").status_code == 200


@pytest.mark.parametrize("path", ["/..%2f..%2fetc%2fpasswd", "/%2e%2e/%2e%2e/etc/passwd"])
def test_path_traversal_falls_back_to_index(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert "<div id=root>" in resp.text


def test_unbuilt_frontend_is_404_but_api_still_works(tmp_path: Path) -> None:
    settings = Settings(public_base_url=PUBLIC_BASE_URL, static_dir=tmp_path / "nope")
    c = TestClient(create_app(settings), base_url=PUBLIC_BASE_URL)
    assert c.get("/jobs").status_code == 404
    assert c.get("/healthz").status_code == 200
