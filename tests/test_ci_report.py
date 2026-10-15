# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""CI's test and coverage reports: the run summary and the coverage badge."""

import json
import re
from pathlib import Path

import pytest

from app.ci_report import COVERAGE_FLOOR, badge, main, summary

# The shapes pytest and Vitest write: one <testsuite>, or one per file under <testsuites>.
PYTEST_JUNIT = """<?xml version="1.0"?><testsuites name="pytest tests">
<testsuite name="pytest" errors="1" failures="2" skipped="3" tests="50"/></testsuites>"""
VITEST_JUNIT = """<?xml version="1.0"?>
<testsuites name="vitest tests" tests="12" failures="0" errors="0">
<testsuite name="a.test.tsx" tests="5" failures="0" errors="0" skipped="1"/>
<testsuite name="b.test.tsx" tests="7" failures="0" errors="0" skipped="0"/></testsuites>"""


def cobertura(tmp_path: Path, name: str, line_rate: str) -> Path:
    path = tmp_path / f"{name}.xml"
    path.write_text(f'<?xml version="1.0"?><coverage line-rate="{line_rate}"/>')
    return path


def junit(tmp_path: Path, name: str, xml: str) -> Path:
    path = tmp_path / f"{name}.junit.xml"
    path.write_text(xml)
    return path


@pytest.mark.parametrize(
    ("xml", "line_rate", "expected"),
    [
        (
            PYTEST_JUNIT,
            "0.9812",
            "### Stack\n\n❌ **44 passed**, 3 failed, 3 skipped\n"
            "✅ **98.12%** line coverage (the floor is 95%)\n",
        ),
        (
            VITEST_JUNIT,
            "0.9499",
            "### Stack\n\n✅ **11 passed**, 0 failed, 1 skipped\n"
            "❌ **94.99%** line coverage (the floor is 95%)\n",
        ),
    ],
)
def test_summary(tmp_path: Path, xml: str, line_rate: str, expected: str) -> None:
    report = summary("Stack", junit(tmp_path, "j", xml), cobertura(tmp_path, "c", line_rate))
    assert report == expected


def test_summary_without_reports(tmp_path: Path) -> None:
    """The tests crashed before writing anything: say so instead of failing the step."""
    assert summary("Stack", tmp_path / "none.xml", tmp_path / "none.xml") == (
        "### Stack\n\n❌ No test report: the tests didn't run to completion.\n"
        "❌ No coverage report.\n"
    )


@pytest.mark.parametrize(
    ("api", "web", "message", "color"),
    [
        ("0.9812", "0.9595", "API 98% · web 95%", "brightgreen"),
        # Rounded down: 94.99% shows as 94%, never as the floor.
        ("0.9812", "0.9499", "API 98% · web 94%", "red"),
        ("1", "0.95", "API 100% · web 95%", "brightgreen"),
    ],
)
def test_badge(tmp_path: Path, api: str, web: str, message: str, color: str) -> None:
    reports = {"API": cobertura(tmp_path, "api", api), "web": cobertura(tmp_path, "web", web)}
    assert badge(reports) == {
        "schemaVersion": 1,
        "label": "coverage",
        "message": message,
        "color": color,
    }


def test_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    api = cobertura(tmp_path, "api", "0.98")
    assert main(["badge", f"API={api}"]) == 0
    assert json.loads(capsys.readouterr().out)["message"] == "API 98%"

    assert main(["summary", "Backend", str(tmp_path / "none.xml"), str(api)]) == 0
    assert "### Backend" in capsys.readouterr().out

    assert main(["badge"]) == 2
    assert main(["badge", "no-equals-sign"]) == 2


def test_the_floor_matches_the_makefile() -> None:
    makefile = (Path(__file__).parent.parent / "Makefile").read_text()
    match = re.search(r"^COVERAGE_FLOOR := (\d+)$", makefile, re.MULTILINE)
    assert match is not None
    assert int(match.group(1)) == COVERAGE_FLOOR
