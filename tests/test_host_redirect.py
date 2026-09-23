# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .conftest import PUBLIC_BASE_URL


@pytest.fixture
def foreign_client(settings: Settings) -> TestClient:
    """A client hitting the app on a non-canonical host (e.g. Render's onrender.com URL)."""
    return TestClient(
        create_app(settings),
        base_url="https://job-tracker.onrender.com",
        follow_redirects=False,
    )


def test_other_host_is_redirected_with_path_and_query(foreign_client: TestClient) -> None:
    resp = foreign_client.get("/jobs/new?url=https%3A%2F%2Fexample.com&title=Engineer")
    assert resp.status_code == 308
    assert resp.headers["location"] == (
        f"{PUBLIC_BASE_URL}/jobs/new?url=https%3A%2F%2Fexample.com&title=Engineer"
    )


def test_other_host_redirect_preserves_method(foreign_client: TestClient) -> None:
    # 308 (not 301/302) so a POST stays a POST after the redirect.
    resp = foreign_client.post("/api/anything")
    assert resp.status_code == 308


def test_healthz_is_exempt_from_redirect(foreign_client: TestClient) -> None:
    resp = foreign_client.get("/healthz")
    assert resp.status_code == 200


def test_canonical_host_is_not_redirected(client: TestClient) -> None:
    resp = client.get("/jobs", follow_redirects=False)
    assert resp.status_code == 200


def test_port_difference_is_not_a_different_host(settings: Settings) -> None:
    # Local dev: Vite on :5173 proxies to FastAPI on :8000 with the same hostname.
    local = Settings(public_base_url="http://localhost:8000", static_dir=settings.static_dir)
    c = TestClient(create_app(local), base_url="http://localhost:5173", follow_redirects=False)
    assert c.get("/jobs").status_code == 200
