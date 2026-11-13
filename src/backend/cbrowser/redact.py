"""Shared secret redaction (t051 A58).

One rule set for every place that persists or surfaces log text:

- ``scripts/redact_evidence.py`` (gate evidence logs), and
- the Supervisor's Docker error paths (``docker_adapter``), where a raw
  Docker error can carry a proxy URL, a token, or a credential-shaped
  environment value.

Only value shapes are replaced; surrounding text is kept so logs stay
diagnosable.  Rules, in application order:

1. URL userinfo (``scheme://user:password@host``) — proxy URLs are the
   live credential shape in this project's logs.
2. ``Bearer`` tokens.
3. Cookie values: every ``name=value`` pair in a ``Cookie``/``Set-Cookie``
   header (any cookie name, not just the session cookie), plus the known
   session cookie names anywhere they appear.
4. Sensitive key-values (``token``/``password``/``secret``/``api_key``/
   ``authorization`` …): the *whole* quoted value, spaces included, then
   unquoted values.
5. Home directory paths (``/Users/<name>``, ``/home/<name>``,
   ``C:\\Users\\<name>``) — the user segment is replaced, the rest of the
   path is kept.
"""

from __future__ import annotations

import re

REDACTED = "<redacted>"
HOME = "<home>"

_SENSITIVE_KEYS = r"(?:token|password|passwd|secret|api[_-]?key|authorization)"

# URL userinfo: scheme://[user[:password]@]host — the password part is
# optional, the user part may be empty only in degenerate URLs.
_URL_USERINFO_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9+.-]*://)(?:[^/@\s:]+)(?::[^/@\s]*)?@"
)
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_BASIC_RE = re.compile(r"(Basic\s+)[A-Za-z0-9+/=]+", re.IGNORECASE)
_SESSION_COOKIE_RE = re.compile(r"(cbrowser_(?:session|csrf)=)[^;\s\"',]+")
_HOME_POSIX_RE = re.compile(r"(?:/Users/|/home/)[^/\s]+")
_HOME_WINDOWS_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+")

# Sensitive key with a quoted value: the whole value, spaces included.
# A value starting with a Bearer/Basic scheme word is left to the
# scheme rules below, so "Authorization: Bearer <token>" keeps its
# scheme and only the credential is replaced.
_SCHEME_LOOKAHEAD = r"(?![Bb]earer\b|[Bb]asic\b)"
_QUOTED_DQ_RE = re.compile(
    r"(" + _SENSITIVE_KEYS + r"\"?\s*[:=]\s*\")"
    + _SCHEME_LOOKAHEAD
    + r"([^\"]*)(\")",
    re.IGNORECASE,
)
_QUOTED_SQ_RE = re.compile(
    r"(" + _SENSITIVE_KEYS + r"'?\s*[:=]\s*')"
    + _SCHEME_LOOKAHEAD
    + r"([^']*)(')",
    re.IGNORECASE,
)
# Sensitive key with an unquoted value.
_UNQUOTED_RE = re.compile(
    r"(" + _SENSITIVE_KEYS + r"\"?\s*[:=]\s*\"?)"
    + _SCHEME_LOOKAHEAD
    + r"[^\s,\"'};]+",
    re.IGNORECASE,
)

# Cookie header: redact every name=value pair except the non-secret
# cookie attributes (Path, Domain, Expires, Max-Age, SameSite).
_COOKIE_HEADER_RE = re.compile(
    r"(?i)(cookie|set-cookie)([\"']?\s*:\s*[\"']?)([^\r\n\"']*)"
)
_COOKIE_ATTRIBUTES = {"expires", "path", "domain", "max-age", "samesite"}
_COOKIE_PAIR_RE = re.compile(r"([A-Za-z0-9_.\-]+)=[^;\s,]+")


def _redact_cookie_value(match: re.Match[str]) -> str:
    name, sep, value = match.group(1), match.group(2), match.group(3)

    def _pair(pair: re.Match[str]) -> str:
        if pair.group(1).lower() in _COOKIE_ATTRIBUTES:
            return pair.group(0)
        return f"{pair.group(1)}={REDACTED}"

    return f"{name}{sep}{_COOKIE_PAIR_RE.sub(_pair, value)}"


def redact(text: str) -> str:
    """Replace secret-shaped values in ``text`` with ``<redacted>``."""
    text = _URL_USERINFO_RE.sub(r"\1" + REDACTED + "@", text)
    text = _BEARER_RE.sub(r"\1" + REDACTED, text)
    text = _BASIC_RE.sub(r"\1" + REDACTED, text)
    text = _COOKIE_HEADER_RE.sub(_redact_cookie_value, text)
    text = _SESSION_COOKIE_RE.sub(r"\1" + REDACTED, text)
    text = _QUOTED_DQ_RE.sub(r"\1" + REDACTED + r"\3", text)
    text = _QUOTED_SQ_RE.sub(r"\1" + REDACTED + r"\3", text)
    text = _UNQUOTED_RE.sub(r"\1" + REDACTED, text)
    text = _HOME_POSIX_RE.sub(HOME, text)
    text = _HOME_WINDOWS_RE.sub(HOME, text)
    return text


def docker_error_detail(exc: BaseException) -> str:
    """Redacted one-line detail for a Docker failure.

    Falls back to the exception type name when the exception carries no
    message, so callers never lose the failure class entirely.
    """
    detail = redact(str(exc)).strip()
    return detail or type(exc).__name__
