"""Security and argument sanitization for Browser Runtime."""

from __future__ import annotations

import re

RUNTIME_ID_PATTERN = re.compile(r"[a-zA-Z0-9_\-.:]{1,128}")


def validate_runtime_id(value: str) -> str:
    """Require a safe single path component without echoing rejected input."""
    if (
        not isinstance(value, str)
        or not RUNTIME_ID_PATTERN.fullmatch(value)
        or value in (".", "..")
    ):
        raise ValueError("Invalid runtime identity")
    return value
