# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test and coverage reports for CI, from the JUnit and Cobertura files `make test` writes.

    python3 -m app.ci_report summary Backend reports/api/junit.xml reports/api/coverage.xml
        Markdown for the run's summary page (CI appends it to $GITHUB_STEP_SUMMARY).
    python3 -m app.ci_report badge API=<coverage.xml> web=<cobertura-coverage.xml>
        The coverage badge: shields.io endpoint JSON, published with the manual (docs.yml).

Standard library only, and Python 3.12-compatible: CI runs it with the runner's own python3.
"""

import json
import math
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# Line coverage below this fails `make test` (COVERAGE_FLOOR in the Makefile, kept equal by
# a test); the badge turns red below it.
COVERAGE_FLOOR = 95


@dataclass(frozen=True)
class Counts:
    total: int
    failed: int
    skipped: int

    @property
    def passed(self) -> int:
        return self.total - self.failed - self.skipped


def count_tests(junit: Path) -> Counts:
    """Totals over every <testsuite> (pytest writes one, Vitest one per file)."""
    total = failed = skipped = 0
    for suite in ET.parse(junit).getroot().iter("testsuite"):
        total += int(suite.get("tests", 0))
        failed += int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
    return Counts(total, failed, skipped)


def line_coverage(cobertura: Path) -> float:
    """Line coverage as a percentage, from the report's overall line-rate."""
    return float(ET.parse(cobertura).getroot().get("line-rate", 0)) * 100


def percent(value: float) -> str:
    """Rounded down, so 94.99% never shows as 95%: the floor is checked on the real value."""
    return f"{math.floor(value)}%"


def summary(name: str, junit: Path, cobertura: Path) -> str:
    lines = [f"### {name}", ""]
    if junit.is_file():
        counts = count_tests(junit)
        icon = "✅" if counts.failed == 0 else "❌"
        lines.append(
            f"{icon} **{counts.passed} passed**, {counts.failed} failed, {counts.skipped} skipped"
        )
    else:
        lines.append("❌ No test report: the tests didn't run to completion.")
    if cobertura.is_file():
        coverage = line_coverage(cobertura)
        icon = "✅" if coverage >= COVERAGE_FLOOR else "❌"
        lines.append(f"{icon} **{coverage:.2f}%** line coverage (the floor is {COVERAGE_FLOOR}%)")
    else:
        lines.append("❌ No coverage report.")
    return "\n".join(lines) + "\n"


def badge(reports: dict[str, Path]) -> dict[str, object]:
    """One badge for every stack: e.g. "coverage | API 98% · web 95%"."""
    coverages = {name: line_coverage(path) for name, path in reports.items()}
    return {
        "schemaVersion": 1,
        "label": "coverage",
        "message": " · ".join(f"{name} {percent(value)}" for name, value in coverages.items()),
        "color": "brightgreen"
        if all(value >= COVERAGE_FLOOR for value in coverages.values())
        else "red",
    }


def main(argv: list[str]) -> int:
    match argv:
        case ["summary", name, junit, cobertura]:
            print(summary(name, Path(junit), Path(cobertura)))
        case ["badge", *pairs] if pairs and all("=" in pair for pair in pairs):
            reports = {name: Path(path) for name, path in (p.split("=", 1) for p in pairs)}
            print(json.dumps(badge(reports), ensure_ascii=False))
        case _:
            print(__doc__, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
