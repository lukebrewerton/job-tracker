# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import logging

from fastapi.testclient import TestClient

from app.logging_config import JsonFormatter


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
