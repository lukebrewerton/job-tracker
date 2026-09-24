# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured (JSON) logging: one JSON object per line on stdout."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; anything else was passed via `extra=` and is kept —
# except uvicorn's `color_message`, a duplicate of `msg` with ANSI colour codes.
_EXCLUDED_ATTRS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "color_message",
}


# Paths whose query string never reaches the access log. The OIDC callback's carries the
# one-time authorisation code and the state.
_REDACTED_QUERY_PATHS = frozenset({"/auth/callback"})


class RedactQueryFilter(logging.Filter):
    """Replace the query string in uvicorn access-log lines for `_REDACTED_QUERY_PATHS`.

    uvicorn logs `'%s - "%s %s HTTP/%s" %d'` with the path and query as the third argument.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if record.name == "uvicorn.access" and isinstance(args, tuple) and len(args) >= 3:
            path, sep, _ = str(args[2]).partition("?")
            if sep and path in _REDACTED_QUERY_PATHS:
                record.args = (*args[:2], f"{path}?[redacted]", *args[3:])
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _EXCLUDED_ATTRS})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Route the root logger and uvicorn's loggers through a single JSON handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactQueryFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
