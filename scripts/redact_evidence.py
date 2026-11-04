#!/usr/bin/env python3
"""Redact secret-shaped values from gate evidence logs (t028 AC-006).

Reads stdin, writes stdout.  Gate logs inherit the repository evidence
sanitization rules (t024): bearer tokens, session cookies and
token/password/secret key-values must never persist in retained
evidence.  Only value shapes are replaced; surrounding text is kept so
logs stay diagnosable.
"""

from __future__ import annotations

import re
import sys

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1<redacted>"),
    (re.compile(r"(cbrowser_session=)[^;\s]+"), r"\1<redacted>"),
    (
        re.compile(
            r"((?:token|password|passwd|secret|api[_-]?key|authorization)"
            r"\"?\s*[:=]\s*\"?)[^\s,\"'}]+",
            re.IGNORECASE,
        ),
        r"\1<redacted>",
    ),
)


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def main() -> int:
    sys.stdout.write(redact(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
