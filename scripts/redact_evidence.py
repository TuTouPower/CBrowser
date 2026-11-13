#!/usr/bin/env python3
"""Redact secret-shaped values from gate evidence logs (t028 AC-006).

Reads stdin, writes stdout.  Gate logs inherit the repository evidence
sanitization rules (t024): bearer tokens, session cookies and
token/password/secret key-values must never persist in retained
evidence.  Only value shapes are replaced; surrounding text is kept so
logs stay diagnosable.

The rules live in ``cbrowser.redact`` (t051 A58) and are shared with the
Supervisor's Docker error paths, so a credential shape fixed in one
place is fixed in both.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "backend"))

from cbrowser.redact import redact


def main() -> int:
    sys.stdout.write(redact(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
