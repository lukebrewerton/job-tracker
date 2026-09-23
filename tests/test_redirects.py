# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `next` redirect check: same-origin relative paths only, everything else -> "/"."""

import pytest

from app.redirects import DEFAULT_NEXT, safe_next


@pytest.mark.parametrize(
    "candidate",
    [
        "/",
        "/jobs",
        "/jobs/0190f1c2-7e4a-7abc-8def-0123456789ab",
        "/jobs/new?url=https%3A%2F%2Fexample.com%2Fjob%2F1&title=Senior%20Engineer",
        "/interviews?filter=upcoming",
        "/%2F%2Fevil.test",  # percent-encoded: stays a same-origin path
    ],
)
def test_same_origin_paths_are_kept(candidate: str) -> None:
    assert safe_next(candidate) == candidate


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        "",
        123,
        "jobs",  # relative, no leading slash
        "https://evil.test",
        "http://evil.test/jobs",
        "//evil.test",  # protocol-relative
        "//evil.test/jobs",
        "///evil.test",
        "/\\evil.test",  # browsers treat \ as /
        "\\\\evil.test",
        "\\/evil.test",
        "/\t/evil.test",  # browsers strip tabs/newlines -> //evil.test
        "/\n/evil.test",
        "/\r\n/evil.test",
        "/jobs\x00",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "https:evil.test",
        "/auth/login",  # never loop back into sign-in
        "/auth/callback?code=x",
        "/auth",
        "/" + "a" * 2048,  # over the length limit
    ],
)
def test_everything_else_falls_back_to_root(candidate: object) -> None:
    assert safe_next(candidate) == DEFAULT_NEXT
