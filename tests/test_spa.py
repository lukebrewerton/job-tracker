# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import PUBLIC_BASE_URL, make_settings, signed_in


@pytest.mark.parametrize("path", ["/", "/jobs", "/jobs/0190f1c2-7e4a/edit", "/interviews"])
def test_client_routes_get_index_html(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert "<div id=root>" in resp.text
    assert resp.headers["cache-control"] == "no-cache"
    # With the footer's links: the defaults, as no DOCS_URL or SOURCE_URL is set.
    assert (
        '<meta name="jt-docs-url" content="https://job-tracker-docs.job-finder.dev/">' in resp.text
    )
    assert (
        '<meta name="jt-source-url" content="https://github.com/lukebrewerton/job-tracker">'
        in resp.text
    )


def test_the_footer_links_come_from_the_settings(static_dir: Path) -> None:
    settings = make_settings(static_dir).model_copy(
        update={
            "docs_url": "https://docs.example.test/",
            "source_url": 'https://git.example.test/me/fork?a=1&b="2"',
        }
    )
    with TestClient(signed_in(create_app(settings)), base_url=PUBLIC_BASE_URL) as c:
        page = c.get("/jobs").text
    assert '<meta name="jt-docs-url" content="https://docs.example.test/">' in page
    # Escaped, so a value can't break out of the attribute.
    assert 'content="https://git.example.test/me/fork?a=1&amp;b=&quot;2&quot;"' in page


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


@pytest.mark.parametrize(
    "path", ["/api", "/api/v1/unknown", "/api/does/not/exist", "/auth/unknown"]
)
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
    settings = make_settings(tmp_path / "nope")
    c = TestClient(signed_in(create_app(settings)), base_url=PUBLIC_BASE_URL)
    assert c.get("/jobs").status_code == 404
    assert c.get("/healthz").status_code == 200
