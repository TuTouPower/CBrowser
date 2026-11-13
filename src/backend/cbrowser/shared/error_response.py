"""Strict parsing of the unified ErrorResponse shape (t069).

Every API, Gateway and Supervisor error body has exactly one shape
(conventions §7): ``error`` / ``message`` / ``retryable``, plus an
optional structured ``details``. Downstream consumers parse *only* this
shape. A body that deviates — a legacy ``detail`` payload, raw text, a
missing or mistyped field — is not a business result: callers turn the
``None`` returned here into a stable, observable protocol error instead
of silently reading whatever fields happen to be present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorResponse:
    """A validated unified error body."""

    error: str
    message: str
    retryable: bool
    details: Any = None


def parse_error_response(body: Any) -> ErrorResponse | None:
    """Return the parsed body, or ``None`` when it is not conforming.

    Conforming means: a JSON object whose ``error`` and ``message`` are
    non-empty strings and whose ``retryable`` is a boolean. ``details``
    is optional and carried through untouched.
    """
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    message = body.get("message")
    retryable = body.get("retryable")
    if not isinstance(error, str) or not error:
        return None
    if not isinstance(message, str) or not message:
        return None
    if not isinstance(retryable, bool):
        return None
    return ErrorResponse(
        error=error,
        message=message,
        retryable=retryable,
        details=body.get("details"),
    )
