# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Smoke test: the app package imports and the toolchain runs."""

import app


def test_app_package_imports() -> None:
    assert app.__version__ == "0.1.0"
