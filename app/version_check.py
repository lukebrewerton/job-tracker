# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check the app's version: `make version-check` (part of `make lint`).

One version for the whole app, in three places that must agree: pyproject.toml,
app/__init__.py and frontend/package.json. It's semantic versioning with MAJOR equal to
the newest API version served (`API_VERSION`), so 1.x.y serves /api/v1 and the release
that adds /api/v2 is 2.0.0. Releases are cut from it (.github/workflows/release.yml).
"""

import json
import re
import sys
import tomllib
from pathlib import Path

from app import __version__
from app.api import API_VERSION

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def problems(versions: dict[str, str], api_version: int) -> list[str]:
    """What's wrong with these versions (by where they're set), if anything."""
    found = []
    if len(set(versions.values())) > 1:
        listed = ", ".join(f"{where} {version}" for where, version in versions.items())
        found.append(f"The versions differ: {listed}")
    for where, version in versions.items():
        match = SEMVER.fullmatch(version)
        if not match:
            found.append(f"{where}: {version!r} isn't MAJOR.MINOR.PATCH")
        elif int(match[1]) != api_version:
            found.append(
                f"{where}: major version {match[1]} must equal the newest API version "
                f"({api_version}, /api/v{api_version})"
            )
    return found


def main() -> int:
    versions = {
        "pyproject.toml": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
            "version"
        ],
        "app/__init__.py": __version__,
        "frontend/package.json": json.loads((ROOT / "frontend/package.json").read_text())[
            "version"
        ],
    }
    found = problems(versions, API_VERSION)
    for problem in found:
        print(problem, file=sys.stderr)
    if not found:
        print(f"Version {__version__} (API v{API_VERSION}): consistent.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
