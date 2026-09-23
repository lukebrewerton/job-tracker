# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Database-backed sessions: cookie, hashing, expiry, revocation, logout and the
user-scoped database session that row-level security relies on."""

import hashlib
import uuid
from collections.abc import Iterator
from http.cookies import SimpleCookie
from pathlib import Path

import httpx2
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.main import create_app
from app.sessions import COOKIE_NAME, CurrentUserDep, UserDbSession

from .conftest import ALLOWED_EMAIL, PUBLIC_BASE_URL, make_settings
from .test_auth import FakeProvider, _callback, _start_login

NINETY_DAYS = 90 * 24 * 60 * 60


def _with_probe_routes(app: FastAPI) -> FastAPI:
    """Authenticated test-only routes, registered ahead of the SPA catch-all."""
    router = APIRouter(prefix="/api/_probe")

    @router.get("/whoami")
    async def whoami(user: CurrentUserDep, db: UserDbSession) -> dict[str, str | None]:
        setting = await db.execute(text("SELECT current_setting('app.user_id', true)"))
        return {"user_id": str(user.id), "email": user.email, "rls_user": setting.scalar_one()}

    app.router.routes[:0] = router.routes
    return app


def _app(
    static_dir: Path, test_db_url: str, provider: FakeProvider, **overrides: object
) -> FastAPI:
    settings = make_settings(static_dir, test_db_url).model_copy(update=overrides)
    return _with_probe_routes(
        create_app(settings, oidc_transport=httpx2.MockTransport(provider.handle))
    )


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(static_dir: Path, test_db_url: str, provider: FakeProvider) -> Iterator[TestClient]:
    app = _app(static_dir, test_db_url, provider)
    with TestClient(app, base_url=PUBLIC_BASE_URL, follow_redirects=False) as c:
        yield c


async def _user_with_session(
    db_engine: AsyncEngine, email: str = ALLOWED_EMAIL, sessions: int = 1
) -> tuple[uuid.UUID, list[str]]:
    """A user plus N sessions, created directly; returns the raw tokens."""
    tokens = [f"test-token-{uuid.uuid4()}" for _ in range(sessions)]
    async with db_engine.begin() as conn:
        user_id = (
            await conn.execute(
                text("INSERT INTO users (oidc_sub, email) VALUES (:s, :e) RETURNING id"),
                {"s": f"sub-{uuid.uuid4()}", "e": email},
            )
        ).scalar_one()
        for token in tokens:
            await conn.execute(
                text("INSERT INTO sessions (user_id, token_hash) VALUES (:u, :h)"),
                {"u": user_id, "h": hashlib.sha256(token.encode()).hexdigest()},
            )
    return user_id, tokens


async def _sql(db_engine: AsyncEngine, sql: str, **params: object) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(sql), params)


async def _session_count(db_engine: AsyncEngine, user_id: uuid.UUID) -> int:
    async with db_engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT count(*) FROM sessions WHERE user_id = :u"), {"u": user_id}
            )
        ).scalar_one()


def _whoami(client: TestClient, token: str | None) -> httpx2.Response:
    headers = {"cookie": f"{COOKIE_NAME}={token}"} if token else {}
    return client.get("/api/_probe/whoami", headers=headers)


def _session_cookie(resp: httpx2.Response) -> SimpleCookie:
    cookie: SimpleCookie = SimpleCookie()
    for header in resp.headers.get_list("set-cookie"):
        if header.startswith(COOKIE_NAME):
            cookie.load(header)
    return cookie


def _clears_cookie(resp: httpx2.Response) -> bool:
    morsel = _session_cookie(resp).get(COOKIE_NAME)
    return morsel is not None and morsel.value in ("", '""') and morsel["max-age"] == "0"


# --- Sign-in creates a session ----------------------------------------------------------


async def test_sign_in_sets_a_locked_down_host_cookie_and_stores_only_the_hash(
    client: TestClient, provider: FakeProvider, db_engine: AsyncEngine
) -> None:
    query = _start_login(client, provider)
    resp = _callback(client, query["state"])
    assert resp.status_code == 303

    morsel = _session_cookie(resp)[COOKIE_NAME]
    token = morsel.value
    assert len(token) >= 43  # 32 random bytes, base64url
    assert morsel["path"] == "/"
    assert morsel["secure"] is True
    assert morsel["httponly"] is True
    assert morsel["samesite"].lower() == "lax"
    assert morsel["domain"] == ""  # host-only (required by the __Host- prefix)
    assert morsel["max-age"] == str(NINETY_DAYS)

    async with db_engine.connect() as conn:
        stored = (
            await conn.execute(
                text("SELECT token_hash FROM sessions WHERE token_hash = :h"),
                {"h": hashlib.sha256(token.encode()).hexdigest()},
            )
        ).scalar_one()
        raw_anywhere = (
            await conn.execute(
                text("SELECT count(*) FROM sessions WHERE token_hash = :t"), {"t": token}
            )
        ).scalar_one()
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert raw_anywhere == 0

    # And the cookie actually works.
    assert _whoami(client, token).status_code == 200


async def test_every_sign_in_gets_a_fresh_token_and_purges_expired_sessions(
    client: TestClient, provider: FakeProvider, db_engine: AsyncEngine
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    provider.claims = {"sub": sub}
    tokens = []
    for _ in range(2):
        query = _start_login(client, provider)
        tokens.append(_session_cookie(_callback(client, query["state"]))[COOKIE_NAME].value)
    assert tokens[0] != tokens[1]

    async with db_engine.connect() as conn:
        user_id = (
            await conn.execute(text("SELECT id FROM users WHERE oidc_sub = :s"), {"s": sub})
        ).scalar_one()
    await _sql(
        db_engine,
        "UPDATE sessions SET last_seen_at = now() - interval '30 days' WHERE user_id = :u",
        u=user_id,
    )
    query = _start_login(client, provider)
    _callback(client, query["state"])
    assert await _session_count(db_engine, user_id) == 1  # both expired ones purged


# --- Using a session --------------------------------------------------------------------


async def test_user_db_session_scopes_rls_to_the_signed_in_user(
    client: TestClient, db_engine: AsyncEngine
) -> None:
    user_id, (token,) = await _user_with_session(db_engine)
    resp = _whoami(client, token)
    assert resp.status_code == 200
    assert resp.json() == {
        "user_id": str(user_id),
        "email": ALLOWED_EMAIL,
        "rls_user": str(user_id),
    }


def test_no_cookie_is_unauthenticated(client: TestClient) -> None:
    resp = _whoami(client, None)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated"}
    assert "set-cookie" not in resp.headers


@pytest.mark.parametrize("token", ["not-a-real-token", "", "x" * 500])
def test_unknown_or_tampered_token_is_rejected_and_cleared(client: TestClient, token: str) -> None:
    resp = client.get("/api/_probe/whoami", headers={"cookie": f"{COOKIE_NAME}={token}x"})
    assert resp.status_code == 401
    assert _clears_cookie(resp)


# --- Expiry -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ageing",
    [
        "UPDATE sessions SET last_seen_at = now() - interval '15 days' WHERE user_id = :u",
        "UPDATE sessions SET created_at = now() - interval '91 days' WHERE user_id = :u",
    ],
    ids=["idle-14-days", "absolute-90-days"],
)
async def test_expired_session_is_rejected_deleted_and_cleared(
    client: TestClient, db_engine: AsyncEngine, ageing: str
) -> None:
    user_id, (token,) = await _user_with_session(db_engine)
    await _sql(db_engine, ageing, u=user_id)

    resp = _whoami(client, token)

    assert resp.status_code == 401
    assert _clears_cookie(resp)
    assert await _session_count(db_engine, user_id) == 0  # survived the 401's rollback


async def test_active_use_keeps_an_idle_session_alive_until_the_absolute_limit(
    client: TestClient, db_engine: AsyncEngine
) -> None:
    user_id, (token,) = await _user_with_session(db_engine)
    await _sql(
        db_engine,
        "UPDATE sessions SET created_at = now() - interval '89 days', "
        "last_seen_at = now() - interval '13 days' WHERE user_id = :u",
        u=user_id,
    )
    assert _whoami(client, token).status_code == 200


@pytest.mark.parametrize(("seen_ago", "touched"), [("2 hours", True), ("10 minutes", False)])
async def test_last_seen_is_written_at_most_hourly(
    client: TestClient, db_engine: AsyncEngine, seen_ago: str, touched: bool
) -> None:
    user_id, (token,) = await _user_with_session(db_engine)
    await _sql(
        db_engine,
        f"UPDATE sessions SET last_seen_at = now() - interval '{seen_ago}' WHERE user_id = :u",
        u=user_id,
    )
    assert _whoami(client, token).status_code == 200
    async with db_engine.connect() as conn:
        recent = (
            await conn.execute(
                text(
                    "SELECT last_seen_at > now() - interval '1 minute' FROM sessions "
                    "WHERE user_id = :u"
                ),
                {"u": user_id},
            )
        ).scalar_one()
    assert recent is touched


# --- Allow-list re-checked on every request -----------------------------------------------


async def test_removed_from_allow_list_revokes_every_session_but_keeps_data(
    static_dir: Path, test_db_url: str, provider: FakeProvider, db_engine: AsyncEngine
) -> None:
    user_id, tokens = await _user_with_session(db_engine, sessions=2)
    # The same user, but the deployment's allow-list no longer includes them.
    app = _app(
        static_dir, test_db_url, provider, allowed_emails=frozenset({"someone-else@example.test"})
    )
    with TestClient(app, base_url=PUBLIC_BASE_URL) as c:
        resp = _whoami(c, tokens[0])

    assert resp.status_code == 401
    assert _clears_cookie(resp)
    assert await _session_count(db_engine, user_id) == 0  # both sessions revoked
    async with db_engine.connect() as conn:
        still_there = (
            await conn.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": user_id})
        ).scalar_one()
    assert still_there == 1


# --- Logout ---------------------------------------------------------------------------------


async def test_logout_ends_the_session_everywhere(
    client: TestClient, db_engine: AsyncEngine
) -> None:
    user_id, (token,) = await _user_with_session(db_engine)
    assert _whoami(client, token).status_code == 200

    resp = client.post("/auth/logout", headers={"cookie": f"{COOKIE_NAME}={token}"})

    assert resp.status_code == 204
    assert _clears_cookie(resp)
    assert await _session_count(db_engine, user_id) == 0
    # A copy of the old cookie is now worthless (server-side revocation, not just deletion).
    assert _whoami(client, token).status_code == 401


def test_logout_without_a_session_is_harmless(client: TestClient) -> None:
    resp = client.post("/auth/logout")
    assert resp.status_code == 204
    assert _clears_cookie(resp)


async def test_a_get_request_cannot_sign_you_out(
    client: TestClient, db_engine: AsyncEngine
) -> None:
    # e.g. <img src="https://your-instance/auth/logout"> on another site.
    user_id, (token,) = await _user_with_session(db_engine)
    resp = client.get("/auth/logout", headers={"cookie": f"{COOKIE_NAME}={token}"})
    assert resp.status_code != 204
    assert not _clears_cookie(resp)
    assert await _session_count(db_engine, user_id) == 1
    assert _whoami(client, token).status_code == 200


def test_session_settings_validate(static_dir: Path) -> None:
    with pytest.raises(ValueError, match="can't exceed"):
        Settings.model_validate(
            {
                **make_settings(static_dir).model_dump(),
                "session_idle_days": 100,
                "session_max_days": 90,
            }
        )
