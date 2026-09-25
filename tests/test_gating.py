# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What needs a session and what doesn't: pages redirect to sign-in and come back to the
exact URL; built files, health checks and sign-in stay public; API docs are
development-only."""

import hashlib
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app
from app.sessions import COOKIE_NAME

from .conftest import ALLOWED_EMAIL, PUBLIC_BASE_URL, make_settings
from .test_auth import FakeProvider

EXTENSION_URL = (
    "/jobs/new?url=https%3A%2F%2Fcareers.example.test%2Fjobs%2F42&title=Senior%20Engineer"
)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(static_dir: Path, test_db_url: str, provider: FakeProvider) -> Iterator[TestClient]:
    app = create_app(
        make_settings(static_dir, test_db_url), oidc_transport=httpx2.MockTransport(provider.handle)
    )
    with TestClient(app, base_url=PUBLIC_BASE_URL, follow_redirects=False) as c:
        yield c


async def _session_token(db_engine: AsyncEngine, *, expired: bool = False) -> str:
    token = f"gating-{uuid.uuid4()}"
    async with db_engine.begin() as conn:
        user_id = (
            await conn.execute(
                text("INSERT INTO users (oidc_sub, email) VALUES (:s, :e) RETURNING id"),
                {"s": f"sub-{uuid.uuid4()}", "e": ALLOWED_EMAIL},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO sessions (user_id, token_hash, last_seen_at) VALUES (:u, :h, "
                + ("now() - interval '30 days'" if expired else "now()")
                + ")"
            ),
            {"u": user_id, "h": hashlib.sha256(token.encode()).hexdigest()},
        )
    return token


# --- Pages ------------------------------------------------------------------------------


def test_page_without_session_redirects_to_sign_in_with_the_exact_url(client: TestClient) -> None:
    resp = client.get(EXTENSION_URL)
    assert resp.status_code == 302
    location = urlsplit(resp.headers["location"])
    assert location.path == "/auth/login"
    assert parse_qs(location.query)["next"] == [EXTENSION_URL]


async def test_expired_session_redirects_to_sign_in(
    client: TestClient, db_engine: AsyncEngine
) -> None:
    token = await _session_token(db_engine, expired=True)
    resp = client.get("/jobs", headers={"cookie": f"{COOKIE_NAME}={token}"})
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("/auth/login?next=")


async def test_signed_in_page_load_gets_the_app(client: TestClient, db_engine: AsyncEngine) -> None:
    token = await _session_token(db_engine)
    resp = client.get("/jobs", headers={"cookie": f"{COOKIE_NAME}={token}"})
    assert resp.status_code == 200
    assert "<div id=root>" in resp.text


@pytest.mark.parametrize("url", ["/", "/?signed_out=1"])
def test_the_front_page_is_public(client: TestClient, url: str) -> None:
    # It shows "Sign in" when signed out, and is where logout lands.
    resp = client.get(url)
    assert resp.status_code == 200
    assert "<div id=root>" in resp.text


@pytest.mark.parametrize(
    "path", ["/dashboard", "/jobs", "/interviews", "/jobs/new", "/%2F", "/%2Fjobs"]
)
def test_every_other_page_needs_a_session(client: TestClient, path: str) -> None:
    # /%2F arrives as "//": only the exact front page is public, not look-alikes.
    resp = client.get(path)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("/auth/login?next=")


def test_extension_link_survives_the_full_sign_in_round_trip(
    client: TestClient, provider: FakeProvider
) -> None:
    """The extension opens /jobs/new?url=… with no session: sign in, land on that URL."""
    to_login = client.get(EXTENSION_URL)
    to_provider = client.get(to_login.headers["location"])
    query = {k: v[0] for k, v in parse_qs(urlsplit(to_provider.headers["location"]).query).items()}
    provider.nonce, provider.code_challenge = query["nonce"], query["code_challenge"]

    back = client.get("/auth/callback", params={"code": "c", "state": query["state"]})

    assert back.status_code == 303
    assert back.headers["location"] == EXTENSION_URL
    landed = client.get(back.headers["location"])  # the cookie jar now holds the session
    assert landed.status_code == 200
    assert "<div id=root>" in landed.text


@pytest.mark.parametrize(
    "path",
    ["/assets/index-abc123.js", "/favicon.ico", "/healthz", "/auth/denied", "/auth/login"],
)
def test_public_paths_need_no_session(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code in (200, 302, 403)  # login redirects to the provider; denied is 403
    location = resp.headers.get("location", "")
    assert not location.startswith("/auth/login?next="), f"{path} was gated"


def test_unknown_api_path_is_a_json_404_not_a_sign_in_redirect(client: TestClient) -> None:
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/json"


# --- API docs: development only -------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/docs", "/api/openapi.json"])
def test_api_docs_are_off_in_production(static_dir: Path, path: str) -> None:
    settings = make_settings(static_dir).model_copy(update={"environment": "production"})
    with TestClient(create_app(settings), base_url=PUBLIC_BASE_URL) as c:
        resp = c.get(path)
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/json"


def test_api_docs_are_on_in_development(static_dir: Path) -> None:
    settings = make_settings(static_dir).model_copy(update={"environment": "development"})
    with TestClient(create_app(settings), base_url=PUBLIC_BASE_URL) as c:
        assert c.get("/api/docs").status_code == 200
        assert c.get("/api/openapi.json").json()["info"]["title"] == "Job Tracker"


def test_environment_defaults_to_production(static_dir: Path) -> None:
    assert make_settings(static_dir).environment == "production"
