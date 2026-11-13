"""Egress observation: the value object and its validity rules (t052).

Pure domain logic only (t062): this module performs no HTTP, no file
I/O and no environment lookups. The probe implementation that produces
observations (echo fetch + local GeoIP), its echo endpoint set and its
error types live in ``cbrowser.shared.egress``.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

#: How long an ``ok`` observation stays current (AC-007).
OBSERVATION_TTL_SECONDS = 24 * 3600

OBSERVATION_PERSPECTIVE = "browser"


@dataclass(frozen=True)
class EgressObservation:
    """One egress observation.  ``country_code`` is only meaningful while
    :func:`observation_is_current` holds for the proxy's present endpoint
    fingerprint and credential revision."""

    proxy_id: str
    endpoint_fingerprint: str
    credential_revision: int
    perspective: str = OBSERVATION_PERSPECTIVE
    egress_ip: str | None = None
    country_code: str | None = None
    source: str = "supervisor_probe"
    status: str = "ok"  # pending | ok | failed
    error_code: str | None = None
    observed_at: datetime.datetime | None = None
    expires_at: datetime.datetime | None = None


def observation_is_current(
    obs: EgressObservation,
    endpoint_fingerprint: str,
    credential_revision: int,
    now: datetime.datetime,
) -> bool:
    """An observation is current only while it is ``ok``, matches the
    proxy's present endpoint fingerprint *and* credential revision, carries
    both an egress IP and a country, and has not expired (AC-007)."""
    if obs.status != "ok":
        return False
    if obs.endpoint_fingerprint != endpoint_fingerprint:
        return False
    if obs.credential_revision != credential_revision:
        return False
    if not obs.egress_ip or not obs.country_code:
        return False
    if obs.expires_at is not None and now >= obs.expires_at:
        return False
    return True
