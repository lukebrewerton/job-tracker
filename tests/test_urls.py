# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""URL canonicalisation: real-world job URLs, and the parameters that must survive."""

import pytest

from app.urls import TRACKING_PARAMS, canonicalise_url

# (as captured, canonical)
FIXTURES = [
    pytest.param(
        "https://www.linkedin.com/jobs/view/4012345678/?refId=abc%3D%3D&trackingId=xyz"
        "&trk=public_jobs_topcard-title&lipi=urn%3Ali%3Apage",
        "https://www.linkedin.com/jobs/view/4012345678",
        id="linkedin-job-view",
    ),
    pytest.param(
        "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4012345678"
        "&trk=flagship3&refId=abc",
        "https://www.linkedin.com/jobs/collections/recommended?currentJobId=4012345678",
        id="linkedin-currentJobId-survives",
    ),
    pytest.param(
        "https://uk.indeed.com/viewjob?jk=0a1b2c3d4e5f6a7b&from=serp&vjs=3&utm_source=x",
        "https://uk.indeed.com/viewjob?from=serp&jk=0a1b2c3d4e5f6a7b&vjs=3",
        id="indeed-jk-survives",
    ),
    pytest.param(
        "https://uk.indeed.com/jobs?q=platform+engineer&l=London&vjk=0a1b2c3d4e5f6a7b",
        "https://uk.indeed.com/jobs?l=London&q=platform+engineer&vjk=0a1b2c3d4e5f6a7b",
        id="indeed-vjk-survives",
    ),
    pytest.param(
        "https://boards.greenhouse.io/acme/jobs/4567890?gh_src=abc123&gh_jid=4567890",
        "https://boards.greenhouse.io/acme/jobs/4567890?gh_jid=4567890",
        id="greenhouse-gh_src-stripped",
    ),
    pytest.param(
        "https://jobs.lever.co/acme/1b2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e/?lever-source=LinkedIn",
        "https://jobs.lever.co/acme/1b2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e?lever-source=LinkedIn",
        id="lever",
    ),
    pytest.param(
        "https://acme.wd3.myworkdayjobs.com/en-GB/Careers/job/London/Platform-Engineer_R-12345"
        "?source=LinkedIn&utm_medium=social",
        "https://acme.wd3.myworkdayjobs.com/en-GB/Careers/job/London/Platform-Engineer_R-12345"
        "?source=LinkedIn",
        id="workday-source-survives",
    ),
    pytest.param(
        "https://careers.acme.test/job?id=42&ref=homepage&fbclid=IwAR0&gclid=Cj0&_hsenc=p2&mc_cid=1",
        "https://careers.acme.test/job?id=42&ref=homepage",
        id="generic-id-and-ref-survive",
    ),
]


@pytest.mark.parametrize(("url", "expected"), FIXTURES)
def test_real_world_urls(url: str, expected: str) -> None:
    assert canonicalise_url(url) == expected


@pytest.mark.parametrize(("url", "expected"), FIXTURES)
def test_canonicalising_twice_changes_nothing(url: str, expected: str) -> None:
    assert canonicalise_url(expected) == expected


# --- The normalisation rules ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://Careers.ACME.test/Jobs/Platform", "https://careers.acme.test/Jobs/Platform"),
        ("https://acme.test:443/jobs", "https://acme.test/jobs"),
        ("http://acme.test:80/jobs", "http://acme.test/jobs"),
        ("https://acme.test:8443/jobs", "https://acme.test:8443/jobs"),
        ("https://acme.test/jobs#apply", "https://acme.test/jobs"),
        ("https://acme.test/jobs/", "https://acme.test/jobs"),
        ("https://acme.test/jobs//", "https://acme.test/jobs"),
        ("https://acme.test/", "https://acme.test/"),
        ("https://acme.test", "https://acme.test/"),
        ("  https://acme.test/jobs \n", "https://acme.test/jobs"),
        ("https://acme.test/jobs?utm_source=x", "https://acme.test/jobs"),
        ("https://acme.test/jobs?", "https://acme.test/jobs"),
        ("https://acme.test/jobs?b=2&&a=1", "https://acme.test/jobs?a=1&b=2"),
        ("https://[2001:DB8::1]:443/jobs", "https://[2001:db8::1]/jobs"),
        ("https://User:Pass@ACME.test/jobs", "https://User:Pass@acme.test/jobs"),
    ],
)
def test_normalisation(url: str, expected: str) -> None:
    assert canonicalise_url(url) == expected


def test_http_and_https_stay_distinct() -> None:
    assert canonicalise_url("http://acme.test/jobs") != canonicalise_url("https://acme.test/jobs")


def test_path_case_and_www_are_kept() -> None:
    assert canonicalise_url("https://www.acme.test/Jobs/42") == "https://www.acme.test/Jobs/42"


@pytest.mark.parametrize(
    "param", ["UTM_Source=x", "utm_whatever=x", "GCLID=x", "trkinfo=x", "TRKINFO=x", "refid=x"]
)
def test_tracking_names_match_case_insensitively(param: str) -> None:
    assert canonicalise_url(f"https://acme.test/jobs?{param}") == "https://acme.test/jobs"


def test_encoded_tracking_name_is_stripped() -> None:
    assert canonicalise_url("https://acme.test/jobs?utm%5Fsource=x") == "https://acme.test/jobs"


def test_kept_values_keep_their_original_encoding() -> None:
    url = "https://acme.test/jobs?q=a%20b&r=c+d&blank&empty="
    assert canonicalise_url(url) == "https://acme.test/jobs?blank&empty=&q=a%20b&r=c+d"


def test_repeated_names_keep_their_relative_order() -> None:
    url = "https://acme.test/jobs?tag=b&x=1&tag=a"
    assert canonicalise_url(url) == "https://acme.test/jobs?tag=b&tag=a&x=1"


# --- The list itself ------------------------------------------------------------------------

IDENTIFYING = ["jk", "vjk", "currentJobId", "ref", "source", "id", "gh_jid", "jobId", "req"]


@pytest.mark.parametrize("name", IDENTIFYING)
def test_identifying_parameters_are_never_stripped(name: str) -> None:
    url = f"https://acme.test/jobs?{name}=42"
    assert canonicalise_url(url) == url


@pytest.mark.parametrize("name", IDENTIFYING)
def test_identifying_parameters_are_not_on_the_list(name: str) -> None:
    lowered = {p.lower() for p in TRACKING_PARAMS}
    assert name.lower() not in lowered
    assert not any(p.endswith("*") and name.lower().startswith(p[:-1]) for p in lowered)


def test_the_list_is_exactly_the_agreed_one() -> None:
    # Extending it is fine: update this test in the same change, deliberately.
    agreed = {
        "utm_*",
        *("gclid", "gbraid", "wbraid", "dclid", "fbclid", "msclkid", "twclid", "li_fat_id"),
        *("mc_cid", "mc_eid", "_hsenc", "_hsmi"),
        *("trk", "trkInfo", "refId", "trackingId", "lipi", "gh_src"),
    }
    assert set(TRACKING_PARAMS) == agreed


# --- Invalid input --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "",
        "acme.test/jobs",
        "ftp://acme.test/jobs",
        "javascript:alert(1)",
        "mailto:jobs@acme.test",
        "https://",
        "https:///jobs",
        "https://acme.test:notaport/jobs",
    ],
)
def test_non_http_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        canonicalise_url(url)
