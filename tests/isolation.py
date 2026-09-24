# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-user isolation harness.

Every /api route must have an `IsolationCase` registered in `CASES`: how to create user
A's data, and what user B must get back when they aim the route at it (404 for a single
item — never 403, which would confirm it exists — or an empty result for lists and
aggregates). `test_isolation.py` fails the build if any /api route has no case.

Adding an API route? Register its case here in the same PR:

    register(IsolationCase("GET", "/api/jobs/{job_id}", arrange=_alices_job, expect=NOT_FOUND))
"""

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.sessions import COOKIE_NAME

from .conftest import ALLOWED_EMAIL

NOT_FOUND: Literal["not_found"] = "not_found"
EMPTY: Literal["empty"] = "empty"

# Framework-provided documentation routes (development only), not data routes.
DOC_PATHS = frozenset({"/api/openapi.json", "/api/docs", "/api/docs/oauth2-redirect"})

# Creates user A's data, with row-level security scoped to A; returns path params.
Arrange = Callable[[AsyncConnection, uuid.UUID], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class IsolationCase:
    method: str
    path: str  # the route template, e.g. "/api/jobs/{job_id}"
    arrange: Arrange
    expect: Literal["not_found", "empty"]
    body: dict[str, Any] | None = None
    # For EMPTY: how to tell a response holds none of A's data.
    is_empty: Callable[[Any], bool] = lambda payload: payload in ([], {}, None)

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)


CASES: dict[tuple[str, str], IsolationCase] = {}


def register(case: IsolationCase, registry: dict[tuple[str, str], IsolationCase] = CASES) -> None:
    if case.key in registry:
        raise ValueError(f"Duplicate isolation case for {case.key}")
    registry[case.key] = case


def api_routes(app: FastAPI) -> set[tuple[str, str]]:
    """Every (method, path) under /api, including routes on included (nested) routers."""
    routes: set[tuple[str, str]] = set()
    for route in iter_route_contexts(app.routes):
        path, methods = route.path, route.methods
        if not path or not methods or not path.startswith("/api/") or path in DOC_PATHS:
            continue
        routes |= {(m, path) for m in methods - {"HEAD", "OPTIONS"}}
    return routes


def openapi_routes(app: FastAPI) -> set[tuple[str, str]]:
    """The same set according to the OpenAPI schema: an independent cross-check."""
    return {
        (method.upper(), path)
        for path, operations in app.openapi().get("paths", {}).items()
        if path.startswith("/api/")
        for method in operations
    }


async def new_user(
    engine: AsyncEngine, *, with_session: bool = False, email: str | None = None
) -> tuple[uuid.UUID, str]:
    """A user (and optionally a session); returns (user_id, raw session token or "")."""
    token = f"isolation-{uuid.uuid4()}" if with_session else ""
    async with engine.begin() as conn:
        user_id: uuid.UUID = (
            await conn.execute(
                text("INSERT INTO users (oidc_sub, email) VALUES (:s, :e) RETURNING id"),
                {"s": f"sub-{uuid.uuid4()}", "e": email or f"{uuid.uuid4().hex[:10]}@example.test"},
            )
        ).scalar_one()
        if with_session:
            await conn.execute(
                text("INSERT INTO sessions (user_id, token_hash) VALUES (:u, :h)"),
                {"u": user_id, "h": hashlib.sha256(token.encode()).hexdigest()},
            )
    return user_id, token


async def run_case(client: TestClient, engine: AsyncEngine, case: IsolationCase) -> None:
    """Create A's data, then aim the route at it as B, and check B learns nothing."""
    alice, _ = await new_user(engine)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(alice)})
        params = await case.arrange(conn, alice)
    # B must be a genuinely signed-in, allowed user: otherwise the allow-list check turns
    # every request into a 401, and cases would "pass" without testing isolation at all.
    _, bob_token = await new_user(engine, with_session=True, email=ALLOWED_EMAIL)

    resp = client.request(
        case.method,
        case.path.format(**params),
        headers={"cookie": f"{COOKIE_NAME}={bob_token}"},
        json=case.body if case.method in {"POST", "PUT", "PATCH"} else None,
    )
    where = f"{case.method} {case.path}"
    assert resp.status_code != 401, f"{where}: B's session was rejected; isolation untested"
    if case.expect == NOT_FOUND:
        assert resp.status_code == 404, f"{where}: expected 404, got {resp.status_code}"
    else:
        assert resp.status_code == 200, f"{where}: expected 200, got {resp.status_code}"
        assert case.is_empty(resp.json()), f"{where}: leaked {resp.json()!r}"
