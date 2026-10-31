"""Verification of Selkies 2.1.0 official web client vendoring and hash verification."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path so scripts can be imported
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.vendor_selkies_web import (  # noqa: E402
    PINNED_SELKIES_VERSION,
    PINNED_WHEEL_SHA256,
)


def test_pinned_constants() -> None:
    assert PINNED_SELKIES_VERSION == "2.1.0"
    assert (
        PINNED_WHEEL_SHA256
        == "8bde6207ca921cb2f38c3204fafe18d40b5578165894818ae1ca9e46fca7b966"
    )
