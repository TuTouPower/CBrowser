"""The one delivery-outcome classification for forwarded payloads (t062).

Both Supervisor delivery paths (runtime events and artifact downloads)
classify a non-200 response through this single rule so the outcomes
can never drift apart.
"""

from __future__ import annotations

DELIVERED = "delivered"
REJECTED = "rejected"
UNAVAILABLE = "unavailable"

# Auth, throttling and transient gateway statuses must never be mistaken for
# a permanent semantic rejection: the payload stays queued for a later retry.
RETRYABLE_4XX = frozenset({401, 403, 408, 429})


def classify_delivery_status(status_code: int) -> str:
    """Map an HTTP status to the delivery outcome for a non-200 response."""
    if status_code in RETRYABLE_4XX or status_code >= 500:
        return UNAVAILABLE
    if 400 <= status_code < 500:
        return REJECTED
    return UNAVAILABLE
