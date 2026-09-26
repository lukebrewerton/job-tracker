# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sign-in flow against a fake OIDC provider that issues real signed ID tokens.

An httpx2 MockTransport stands in for the provider's discovery document, signing keys
and token endpoint.
Tokens are genuinely RS256-signed, so Authlib's validation (signature, issuer, audience,
expiry, nonce) really runs — the tests prove bad tokens are rejected, not just that we
call a library.
"""

import base64
import hashlib
import html
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app

from .conftest import (
    ALLOWED_EMAIL,
    OIDC_CLIENT_ID,
    OIDC_ISSUER,
    PUBLIC_BASE_URL,
    make_settings,
)

SIGNING_KEY = RSAKey.generate_key(2048, parameters={"kid": "test-key"})
ATTACKER_KEY = RSAKey.generate_key(2048, parameters={"kid": "test-key"})


@dataclass
class FakeProvider:
    """What the fake token endpoint should return for the next exchange."""

    claims: dict[str, Any] = field(default_factory=dict)
    signing_key: RSAKey = field(default_factory=lambda: SIGNING_KEY)
    include_id_token: bool = True
    nonce: str | None = None  # captured from the authorisation redirect
    code_challenge: str | None = None  # likewise: PKCE is enforced like a real provider

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        """The whole fake provider: discovery, signing keys and the token endpoint."""
        url = str(request.url)
        if url == f"{OIDC_ISSUER}/.well-known/openid-configuration":
            return httpx2.Response(
                200,
                json={
                    "issuer": OIDC_ISSUER,
                    "authorization_endpoint": f"{OIDC_ISSUER}/authorize",
                    "token_endpoint": f"{OIDC_ISSUER}/token",
                    "jwks_uri": f"{OIDC_ISSUER}/jwks",
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if url == f"{OIDC_ISSUER}/jwks":
            return httpx2.Response(200, json={"keys": [SIGNING_KEY.as_dict(private=False)]})
        if url == f"{OIDC_ISSUER}/token" and request.method == "POST":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            if not self._pkce_ok(form.get("code_verifier")):
                return httpx2.Response(400, json={"error": "invalid_grant"})
            return self.token_response()
        return httpx2.Response(404)

    def _pkce_ok(self, verifier: str | None) -> bool:
        if not verifier or not self.code_challenge:
            return False
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == self.code_challenge

    def token_response(self) -> httpx2.Response:
        body: dict[str, Any] = {"access_token": "at", "token_type": "Bearer", "expires_in": 3600}
        if self.include_id_token:
            now = int(time.time())
            claims = {
                "iss": OIDC_ISSUER,
                "aud": OIDC_CLIENT_ID,
                "sub": f"sub-{uuid.uuid4()}",
                "email": ALLOWED_EMAIL,
                "email_verified": True,
                "nonce": self.nonce,
                "iat": now,
                "exp": now + 600,
                **self.claims,
            }
            header = {"alg": "RS256", "kid": "test-key"}
            body["id_token"] = jwt.encode(header, claims, self.signing_key)
        return httpx2.Response(200, json=body)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(static_dir: Path, test_db_url: str, provider: FakeProvider) -> Iterator[TestClient]:
    app = create_app(
        make_settings(static_dir, test_db_url),
        oidc_transport=httpx2.MockTransport(provider.handle),
    )
    with TestClient(app, base_url=PUBLIC_BASE_URL, follow_redirects=False) as c:
        yield c


def _start_login(client: TestClient, provider: FakeProvider, **params: str) -> dict[str, str]:
    resp = client.get("/auth/login", params=params)
    assert resp.status_code == 302
    location = urlsplit(resp.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{OIDC_ISSUER}/authorize"
    query = {k: v[0] for k, v in parse_qs(location.query).items()}
    provider.nonce = query.get("nonce")
    provider.code_challenge = query.get("code_challenge")
    return query


def _callback(client: TestClient, state: str, **extra: str) -> httpx2.Response:
    return client.get("/auth/callback", params={"code": "auth-code", "state": state, **extra})


async def _user_by_sub(db_engine: AsyncEngine, sub: str) -> tuple[uuid.UUID, str] | None:
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT id, email FROM users WHERE oidc_sub = :s"), {"s": sub})
        ).one_or_none()
    return (row.id, row.email) if row else None


# --- /auth/login ------------------------------------------------------------------------


def test_login_redirects_to_provider_with_minimal_scope(
    client: TestClient, provider: FakeProvider
) -> None:
    query = _start_login(client, provider, next="/jobs")
    assert query["scope"] == "openid email"
    assert query["client_id"] == OIDC_CLIENT_ID
    assert query["redirect_uri"] == f"{PUBLIC_BASE_URL}/auth/callback"
    assert query["state"] and query["nonce"]
    assert "prompt" not in query


def test_login_uses_pkce_s256(client: TestClient, provider: FakeProvider) -> None:
    query = _start_login(client, provider)
    assert query["code_challenge_method"] == "S256"
    assert len(query["code_challenge"]) >= 43  # base64url SHA-256, never the verifier
    assert "code_verifier" not in query


def test_code_exchange_without_the_matching_pkce_verifier_fails(
    client: TestClient, provider: FakeProvider
) -> None:
    # A stolen code replayed by someone else: they can't know the verifier, so the
    # provider (enforcing PKCE, like Google) refuses the exchange.
    query = _start_login(client, provider)
    provider.code_challenge = "challenge-for-a-different-login"
    assert _callback(client, query["state"]).headers["location"] == "/auth/denied?reason=failed"


def test_login_cookie_is_scoped_short_lived_and_locked_down(
    client: TestClient, provider: FakeProvider
) -> None:
    resp = client.get("/auth/login")
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith("jt_oauth=")
    for attribute in ("path=/auth", "httponly", "secure", "samesite=lax", "max-age=600"):
        assert attribute in cookie.lower(), attribute


def test_switch_account_asks_provider_for_the_account_chooser(
    client: TestClient, provider: FakeProvider
) -> None:
    query = _start_login(client, provider, switch_account="true")
    assert query["prompt"] == "select_account"


# --- Successful sign-in -----------------------------------------------------------------


async def test_allowed_verified_email_creates_user_and_returns_to_next(
    client: TestClient, provider: FakeProvider, db_engine: AsyncEngine
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    provider.claims = {"sub": sub, "email": "Allowed@Example.TEST"}  # case-insensitive
    query = _start_login(client, provider, next="/jobs/new?url=https%3A%2F%2Fx.test&title=Eng")

    resp = _callback(client, query["state"])

    assert resp.status_code == 303
    assert resp.headers["location"] == "/jobs/new?url=https%3A%2F%2Fx.test&title=Eng"
    user = await _user_by_sub(db_engine, sub)
    assert user is not None
    assert user[1] == ALLOWED_EMAIL  # stored lowercase


async def test_unsafe_next_falls_back_to_root(client: TestClient, provider: FakeProvider) -> None:
    query = _start_login(client, provider, next="//evil.test/phish")
    resp = _callback(client, query["state"])
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_returning_user_with_changed_email_updates_the_same_row(
    client: TestClient, provider: FakeProvider, db_engine: AsyncEngine
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    async with db_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (oidc_sub, email) VALUES (:s, 'old@example.test')"),
            {"s": sub},
        )
    before = await _user_by_sub(db_engine, sub)
    provider.claims = {"sub": sub}  # now signs in with ALLOWED_EMAIL

    query = _start_login(client, provider)
    assert _callback(client, query["state"]).status_code == 303

    after = await _user_by_sub(db_engine, sub)
    assert before is not None and after is not None
    assert after == (before[0], ALLOWED_EMAIL)


async def test_same_email_with_a_new_sub_is_a_new_user(
    client: TestClient, provider: FakeProvider, db_engine: AsyncEngine
) -> None:
    # A recycled email address must not inherit someone else's account.
    old_sub, new_sub = f"sub-{uuid.uuid4()}", f"sub-{uuid.uuid4()}"
    async with db_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (oidc_sub, email) VALUES (:s, :e)"),
            {"s": old_sub, "e": ALLOWED_EMAIL},
        )
    provider.claims = {"sub": new_sub}
    query = _start_login(client, provider)
    assert _callback(client, query["state"]).status_code == 303

    old, new = await _user_by_sub(db_engine, old_sub), await _user_by_sub(db_engine, new_sub)
    assert old is not None and new is not None
    assert old[0] != new[0]


# --- Refused: not authorised --------------------------------------------------------------


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "stranger@example.test"},
        {"email_verified": False},
        {"email_verified": "true"},  # must be the boolean true, not a truthy string
        {"email_verified": None},
        {"email": None},
    ],
    ids=["not-on-list", "unverified", "verified-as-string", "verified-missing", "no-email"],
)
async def test_refused_sign_in_creates_nothing(
    client: TestClient, provider: FakeProvider, db_engine: AsyncEngine, claims: dict[str, Any]
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    provider.claims = {"sub": sub, **claims}
    query = _start_login(client, provider)

    resp = _callback(client, query["state"])

    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/denied"
    assert await _user_by_sub(db_engine, sub) is None


# --- Failed: bad or unverifiable tokens and flows -----------------------------------------


@pytest.mark.parametrize(
    ("claims", "signing_key"),
    [
        ({}, ATTACKER_KEY),  # signature doesn't verify
        ({"nonce": "replayed-nonce"}, SIGNING_KEY),
        ({"aud": "someone-elses-client"}, SIGNING_KEY),
        ({"iss": "https://evil.test"}, SIGNING_KEY),
        ({"exp": int(time.time()) - 3600}, SIGNING_KEY),  # well past the 2-minute leeway
    ],
    ids=["tampered-signature", "wrong-nonce", "wrong-audience", "wrong-issuer", "expired"],
)
async def test_invalid_id_token_fails_sign_in(
    client: TestClient,
    provider: FakeProvider,
    db_engine: AsyncEngine,
    claims: dict[str, Any],
    signing_key: RSAKey,
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    provider.claims = {"sub": sub, **claims}
    provider.signing_key = signing_key
    query = _start_login(client, provider)

    resp = _callback(client, query["state"])

    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/denied?reason=failed"
    assert await _user_by_sub(db_engine, sub) is None


def test_token_response_without_id_token_fails(client: TestClient, provider: FakeProvider) -> None:
    provider.include_id_token = False
    query = _start_login(client, provider)
    assert _callback(client, query["state"]).headers["location"] == "/auth/denied?reason=failed"


def test_state_mismatch_fails(client: TestClient, provider: FakeProvider) -> None:
    _start_login(client, provider)
    resp = _callback(client, "attacker-chosen-state")
    assert resp.headers["location"] == "/auth/denied?reason=failed"


def test_callback_without_login_cookie_fails(
    static_dir: Path, test_db_url: str, provider: FakeProvider
) -> None:
    # e.g. a forged callback link, or the 10-minute login cookie expired.
    app = create_app(
        make_settings(static_dir, test_db_url),
        oidc_transport=httpx2.MockTransport(provider.handle),
    )
    with TestClient(app, base_url=PUBLIC_BASE_URL, follow_redirects=False) as fresh:
        resp = _callback(fresh, "some-state")
    assert resp.headers["location"] == "/auth/denied?reason=failed"


def test_cancelled_consent_fails(client: TestClient, provider: FakeProvider) -> None:
    query = _start_login(client, provider)
    resp = _callback(client, query["state"], error="access_denied")
    assert resp.headers["location"] == "/auth/denied?reason=failed"


def test_login_state_cannot_be_replayed(client: TestClient, provider: FakeProvider) -> None:
    query = _start_login(client, provider)
    assert _callback(client, query["state"]).status_code == 303
    # Same state again: it was consumed by the first callback.
    assert _callback(client, query["state"]).headers["location"] == "/auth/denied?reason=failed"


# --- /auth/denied -------------------------------------------------------------------------


def test_denied_page_offers_a_different_account(client: TestClient) -> None:
    resp = client.get("/auth/denied")
    assert resp.status_code == 403
    assert "isn&#x27;t authorised" in resp.text
    assert 'href="/auth/login?switch_account=true"' in resp.text
    assert resp.headers["cache-control"] == "no-store"


def test_failed_page_offers_a_retry_and_reveals_nothing(client: TestClient) -> None:
    resp = client.get("/auth/denied", params={"reason": "failed"})
    assert resp.status_code == 400
    assert "Sign-in failed" in resp.text
    assert 'href="/auth/login"' in resp.text


# --- Keeping the destination through a refused sign-in ------------------------------------

EXTENSION_NEXT = "/jobs/new?url=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fview%2F42&title=SRE"


def test_a_refused_sign_in_remembers_where_you_were_going(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.claims = {"sub": f"sub-{uuid.uuid4()}", "email": "stranger@example.test"}
    query = _start_login(client, provider, next=EXTENSION_NEXT)

    resp = _callback(client, query["state"])

    assert resp.status_code == 303
    location = urlsplit(resp.headers["location"])
    assert location.path == "/auth/denied"
    assert parse_qs(location.query) == {"next": [EXTENSION_NEXT]}


def test_the_different_account_button_goes_back_to_where_you_were_going(
    client: TestClient,
) -> None:
    resp = client.get("/auth/denied", params={"next": EXTENSION_NEXT})
    href = html.unescape(re.search(r'href="([^"]+)"', resp.text).group(1))  # type: ignore[union-attr]
    target = urlsplit(href)
    assert target.path == "/auth/login"
    assert parse_qs(target.query) == {"switch_account": ["true"], "next": [EXTENSION_NEXT]}


def test_try_again_also_keeps_the_destination(client: TestClient) -> None:
    resp = client.get("/auth/denied", params={"reason": "failed", "next": "/jobs?status=all"})
    href = html.unescape(re.search(r'href="([^"]+)"', resp.text).group(1))  # type: ignore[union-attr]
    assert parse_qs(urlsplit(href).query) == {"next": ["/jobs?status=all"]}


@pytest.mark.parametrize(
    "evil", ["https://evil.test/", "//evil.test", "/\\evil.test", "javascript:alert(1)"]
)
def test_the_denied_page_never_links_off_site(client: TestClient, evil: str) -> None:
    resp = client.get("/auth/denied", params={"next": evil})
    assert 'href="/auth/login?switch_account=true"' in resp.text
    assert "evil" not in resp.text


def test_the_denied_page_escapes_its_link(client: TestClient) -> None:
    resp = client.get("/auth/denied", params={"next": '/jobs?q="><script>'})
    assert "<script>" not in resp.text
