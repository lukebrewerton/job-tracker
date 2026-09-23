# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-site request forgery defences: the Origin check and JSON-only API writes.

The Origin check matters because SameSite=Lax treats every *.job-finder.dev app as the
same site, so a compromised sibling subdomain could otherwise post with our cookie.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import PUBLIC_BASE_URL, make_settings


@pytest.fixture
def client(static_dir: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(static_dir))
    # An unauthenticated test-only endpoint, so "allowed through" is a plain 200.
    router = APIRouter()

    @router.api_route("/api/_csrf_probe", methods=["POST", "PUT", "PATCH", "DELETE", "GET"])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    app.router.routes[:0] = router.routes
    with TestClient(app, base_url=PUBLIC_BASE_URL) as c:
        yield c


JSON = {"content-type": "application/json"}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.test",
        "https://other-app.job-finder.dev",  # a sibling subdomain: same *site*, not our origin
        "http://job-tracker.example.test",  # our host, but downgraded to http
        "null",  # sandboxed iframes, some redirects
    ],
)
def test_foreign_origin_writes_are_refused(client: TestClient, method: str, origin: str) -> None:
    resp = client.request(method, "/api/_csrf_probe", headers={**JSON, "origin": origin}, json={})
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Cross-origin request refused"}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "origin",
    [
        PUBLIC_BASE_URL,
        "https://JOB-TRACKER.example.test",  # hostnames are case-insensitive
        "https://job-tracker.example.test:8443",  # port ignored (dev: Vite vs FastAPI ports)
        None,  # non-browser clients send no Origin
    ],
)
def test_same_origin_or_originless_writes_are_allowed(
    client: TestClient, method: str, origin: str | None
) -> None:
    headers = {**JSON, **({"origin": origin} if origin else {})}
    resp = client.request(method, "/api/_csrf_probe", headers=headers, json={})
    assert resp.status_code == 200


def test_reads_are_never_blocked_by_origin(client: TestClient) -> None:
    resp = client.get("/api/_csrf_probe", headers={"origin": "https://evil.test"})
    assert resp.status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
@pytest.mark.parametrize(
    "content_type",
    [None, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"],
)
def test_api_writes_must_be_json(client: TestClient, method: str, content_type: str | None) -> None:
    headers = {"content-type": content_type} if content_type else {}
    resp = client.request(method, "/api/_csrf_probe", headers=headers, content=b"a=1")
    assert resp.status_code == 415


def test_json_with_charset_is_fine(client: TestClient) -> None:
    headers = {"content-type": "application/json; charset=utf-8"}
    resp = client.post("/api/_csrf_probe", headers=headers, content=b"{}")
    assert resp.status_code == 200


def test_bodiless_delete_needs_no_content_type(client: TestClient) -> None:
    # fetch(url, {method: "DELETE"}) sends no Content-Type; a cross-origin DELETE already
    # needs a CORS preflight, so it isn't a form-submittable threat.
    assert client.delete("/api/_csrf_probe").status_code == 200


def test_logout_from_a_foreign_origin_is_refused(client: TestClient) -> None:
    resp = client.post("/auth/logout", headers={"origin": "https://other-app.job-finder.dev"})
    assert resp.status_code == 403


def test_logout_from_our_origin_is_allowed(client: TestClient) -> None:
    assert client.post("/auth/logout", headers={"origin": PUBLIC_BASE_URL}).status_code == 204
