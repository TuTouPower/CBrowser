"""Cross-service error types surfaced through the Control API."""

from __future__ import annotations


class ServiceNotConfiguredError(Exception):
    """A required internal service surface is not configured.

    Distinct from DatabaseLockError: a missing service token or service is a
    deployment configuration problem, so the API reports it with the
    ``service_not_configured`` error code and ``retryable=false`` instead of
    the retryable ``database_busy`` shape.
    """

    def __init__(self, message: str = "Service is not configured"):
        super().__init__(message)
