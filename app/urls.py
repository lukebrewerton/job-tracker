# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Job URL canonicalisation, for de-duplication. Pure: no I/O, no per-site rules.

The design record is "URL canonicalisation" in ARCHITECTURE.md. In short: remove known
tracking parameters from a single global list and normalise the rest, keeping anything
not on the list. A tracking parameter that slips through only lets a duplicate in;
stripping an identifying one would wrongly block a real job, so the list must never
contain one (e.g. Indeed's `jk`/`vjk`, LinkedIn's `currentJobId`, or generic names such
as `ref`, `source` and `id`, which some applicant-tracking systems use as the job ID).
"""

from urllib.parse import unquote_plus, urlsplit, urlunsplit

# Query parameters removed from job URLs, compared case-insensitively. A trailing `*`
# matches by prefix.
TRACKING_PARAMS = frozenset(
    {
        "utm_*",
        "gclid",
        "gbraid",
        "wbraid",
        "dclid",
        "fbclid",
        "msclkid",
        "twclid",
        "li_fat_id",
        "mc_cid",
        "mc_eid",
        "_hsenc",
        "_hsmi",
        "trk",
        "trkInfo",
        "refId",
        "trackingId",
        "lipi",
        "gh_src",
    }
)

_EXACT = frozenset(p.lower() for p in TRACKING_PARAMS if not p.endswith("*"))
_PREFIXES = tuple(p.removesuffix("*").lower() for p in TRACKING_PARAMS if p.endswith("*"))
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _is_tracking(name: str) -> bool:
    return name in _EXACT or name.startswith(_PREFIXES)


def canonicalise_url(url: str) -> str:
    """Return the canonical form of an http(s) URL.

    Lowercases the scheme and host, drops the default port and the fragment, trims
    trailing slashes from the path (an empty path becomes `/`), removes tracking
    parameters, and sorts the rest by name. Each kept parameter keeps its original
    encoding, and repeated names keep their relative order.

    Raises ValueError for anything that isn't an http(s) URL with a host.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise ValueError("URL must start with http:// or https://")
    host = parts.hostname  # already lowercased
    if not host:
        raise ValueError("URL must include a host")
    port = parts.port  # raises ValueError for a malformed port

    netloc = f"[{host}]" if ":" in host else host  # IPv6 literals keep their brackets
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"
    userinfo, at, _ = parts.netloc.rpartition("@")
    if at:
        netloc = f"{userinfo}@{netloc}"

    path = parts.path.rstrip("/") or "/"

    kept = [
        (name, param)
        for param in parts.query.split("&")
        if param and not _is_tracking(name := unquote_plus(param.partition("=")[0]).lower())
    ]
    kept.sort(key=lambda pair: pair[0])  # stable: repeated names keep their order
    query = "&".join(param for _, param in kept)

    return urlunsplit((scheme, netloc, path, query, ""))
