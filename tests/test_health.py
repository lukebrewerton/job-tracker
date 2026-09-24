# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.logging_config import JsonFormatter, RedactQueryFilter, configure_logging


def test_healthz_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_json_log_drops_uvicorn_color_message() -> None:
    record = logging.makeLogRecord(
        {"msg": "Started", "levelname": "INFO", "color_message": "\x1b[36mStarted\x1b[0m"}
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["msg"] == "Started"
    assert "color_message" not in payload


def _access_line(path: str) -> str:
    """Format a uvicorn access-log record for `path` the way the configured handler does."""
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("203.0.113.9:0", "GET", path, "1.1", 303),
        None,
    )
    assert RedactQueryFilter().filter(record)
    return str(json.loads(JsonFormatter().format(record))["msg"])


def test_callback_query_is_redacted_from_the_access_log() -> None:
    line = _access_line("/auth/callback?state=st4te&code=4%2F0secret-code&scope=openid")
    assert "secret-code" not in line
    assert "st4te" not in line
    assert '"GET /auth/callback?[redacted] HTTP/1.1" 303' in line


@pytest.mark.parametrize(
    "path",
    [
        "/auth/callback",
        "/auth/login?next=%2Fjobs",
        "/jobs/new?url=x&title=y",
        "/auth/callbackx?a=1",
    ],
)
def test_other_access_log_paths_are_untouched(path: str) -> None:
    assert f'"GET {path} HTTP/1.1" 303' in _access_line(path)


def test_configured_handler_redacts() -> None:
    configure_logging("INFO")
    (handler,) = logging.getLogger().handlers
    assert any(isinstance(f, RedactQueryFilter) for f in handler.filters)
