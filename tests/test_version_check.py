# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The version rule: one version everywhere, semver, MAJOR = the newest API version."""

import pytest

from app.version_check import main, problems


def test_the_repo_follows_the_rule() -> None:
    assert main() == 0


@pytest.mark.parametrize(
    ("versions", "expected"),
    [
        ({"a": "1.0.0", "b": "1.0.0"}, []),
        ({"a": "1.4.2", "b": "1.4.2"}, []),
        ({"a": "1.0.0", "b": "1.0.1"}, ["The versions differ: a 1.0.0, b 1.0.1"]),
        # A breaking API change (v2) needs a major release, and vice versa.
        ({"a": "2.0.0"}, ["a: major version 2 must equal the newest API version (1, /api/v1)"]),
        ({"a": "0.9.0"}, ["a: major version 0 must equal the newest API version (1, /api/v1)"]),
        ({"a": "1.0"}, ["a: '1.0' isn't MAJOR.MINOR.PATCH"]),
        ({"a": "1.0.0-rc1"}, ["a: '1.0.0-rc1' isn't MAJOR.MINOR.PATCH"]),
    ],
)
def test_problems(versions: dict[str, str], expected: list[str]) -> None:
    assert problems(versions, api_version=1) == expected
