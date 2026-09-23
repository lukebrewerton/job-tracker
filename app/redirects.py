# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validation of post-login redirect targets (`next`), to prevent open redirects.

`next` inevitably travels as a query parameter (e.g. /auth/login?next=...), so the
validation — not where it came from — is the control. Only same-origin, relative paths
are accepted; anything else falls back to "/".
"""

import re
from urllib.parse import urlsplit

DEFAULT_NEXT = "/"
_MAX_LENGTH = 2048
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def safe_next(candidate: object) -> str:
    if not isinstance(candidate, str) or not candidate or len(candidate) > _MAX_LENGTH:
        return DEFAULT_NEXT
    # Exactly one leading slash. "//host" and "/\\host" are protocol-relative URLs to
    # browsers (which also treat "\\" as "/"), i.e. a redirect to another site.
    if not candidate.startswith("/") or candidate.startswith(("//", "/\\")):
        return DEFAULT_NEXT
    # Tabs/newlines are stripped by browsers ("/\t/evil.test" becomes "//evil.test").
    if _CONTROL_CHARS.search(candidate):
        return DEFAULT_NEXT
    parts = urlsplit(candidate)
    if parts.scheme or parts.netloc:
        return DEFAULT_NEXT
    # Never bounce back into the sign-in flow itself.
    if parts.path == "/auth" or parts.path.startswith("/auth/"):
        return DEFAULT_NEXT
    return candidate
