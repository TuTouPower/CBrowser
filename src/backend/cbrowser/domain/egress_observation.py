"""Egress observation: echo fetch + local GeoIP + validity rules (t052).

The egress IP is discovered by asking an IP-echo endpoint *through the
proxy* (never directly from the API process, whose egress may differ from
the Browser's).  The country is then resolved from the egress IP against
the local GeoLite2 database — the IP is never sent to a third-party
geolocation service.

Echo endpoint set: the same three plain-text echo services the
CloakBrowser SDK uses (``cloakbrowser.geoip._IP_ECHO_URLS``); the first
one that returns a parseable IP wins.  Data sent to an echo service is
exactly one HTTPS GET for the caller's own egress IP (the service sees
the egress IP by design — that is its purpose); no credentials, proxy
identity or other data is sent.

This module is deliberately dependency-light (``httpx`` + a lazy
``geoip2`` import) so it can run both in the API process (tests) and in
the probe helper inside the Browser image (``cbrowser.runtime_agent.
egress_probe``), where ``geoip2`` and the mmdb mount are present.
"""

from __future__ import annotations

import datetime
import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from cbrowser.domain.proxy_endpoint import ProxyEndpoint

#: Plain-text IP echo services (same set as the CloakBrowser SDK).
ECHO_URLS: tuple[str, ...] = (
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ifconfig.me/ip",
)

#: How long an ``ok`` observation stays current (AC-007).
OBSERVATION_TTL_SECONDS = 24 * 3600

GEOIP_DB_FILENAME = "GeoLite2-City.mmdb"
OBSERVATION_PERSPECTIVE = "browser"


class EgressProbeError(RuntimeError):
    """Probe failure with a machine-readable ``code`` (no secrets)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GeoIpUnavailableError(RuntimeError):
    """Local GeoIP database / reader unavailable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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


def resolve_geoip_db_path(explicit: str | Path | None = None) -> Path | None:
    """Locate ``GeoLite2-City.mmdb``.

    Precedence: explicit path, ``CBROWSER_GEOIP_DB`` (file),
    ``CBROWSER_GEOIP_CACHE`` (directory, set by compose) /
    ``GeoLite2-City.mmdb``.  Returns ``None`` when nothing is configured.
    """
    if explicit is not None:
        return Path(explicit)
    env_file = os.environ.get("CBROWSER_GEOIP_DB")
    if env_file:
        return Path(env_file)
    cache_dir = os.environ.get("CBROWSER_GEOIP_CACHE")
    if cache_dir:
        return Path(cache_dir) / GEOIP_DB_FILENAME
    return None


class GeoIpLookup:
    """Country lookup against the local GeoLite2 database.

    ``geoip2`` is imported lazily: the API/Supervisor images do not ship
    it, only the Browser image does (``cloakbrowser[geoip]``).  A missing
    database or reader is a hard failure (``GeoIpUnavailableError``) — the
    observation is recorded as failed, never guessed.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = resolve_geoip_db_path(db_path)

    def country_code(self, ip: str) -> str | None:
        if self.db_path is None or not self.db_path.is_file():
            raise GeoIpUnavailableError(
                "geoip_db_missing",
                "GeoLite2 database is unavailable",
            )
        try:
            import geoip2.database
        except ImportError:
            raise GeoIpUnavailableError(
                "geoip2_missing",
                "geoip2 package is not installed in this image",
            ) from None
        try:
            with geoip2.database.Reader(str(self.db_path)) as reader:
                response = reader.city(ip)
                code = response.country.iso_code
        except Exception as exc:
            raise GeoIpUnavailableError(
                "geoip_lookup_failed",
                f"GeoIP lookup failed: {type(exc).__name__}",
            ) from None
        return code.upper() if code else None


def fetch_egress_ip(
    proxy_url: str | None,
    echo_urls: tuple[str, ...] | list[str] = ECHO_URLS,
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Discover the egress IP by asking echo services through ``proxy_url``.

    ``proxy_url`` is the full endpoint URL (with credentials); ``None``
    fetches directly (only used by tests / the API-egress control).  The
    first echo service returning a parseable IP wins.
    """
    last_error: EgressProbeError | None = None
    try:
        # trust_env=False: only the explicitly passed proxy may be used.
        # An ambient HTTP(S)_PROXY would silently change the egress path
        # (and leak the probe through an unrelated proxy).
        with httpx.Client(
            proxy=proxy_url or None,
            timeout=timeout,
            transport=transport,
            trust_env=False,
        ) as client:
            for url in echo_urls:
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    candidate = resp.text.strip()
                    ipaddress.ip_address(candidate)
                    return candidate
                except httpx.UnsupportedProtocol:
                    raise EgressProbeError(
                        "echo_proxy_unsupported",
                        "proxy scheme is not supported by the echo client",
                    ) from None
                except (ValueError, httpx.HTTPError) as exc:
                    if isinstance(exc, ValueError):
                        last_error = EgressProbeError(
                            "invalid_echo_response",
                            "echo service did not return an IP address",
                        )
                    else:
                        last_error = EgressProbeError(
                            "echo_unreachable",
                            f"echo service unreachable: {type(exc).__name__}",
                        )
                    continue
    except EgressProbeError:
        raise
    if last_error is not None:
        raise last_error
    raise EgressProbeError("echo_unreachable", "no echo service responded")


def probe_egress(
    endpoint: ProxyEndpoint,
    echo_urls: tuple[str, ...] | list[str] = ECHO_URLS,
    geoip: GeoIpLookup | None = None,
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str | None]:
    """Probe one endpoint: egress IP through the proxy, then local country.

    Returns ``(egress_ip, country_code)``.  Raises
    :class:`EgressProbeError` (``geoip_db_missing`` etc.) when the country
    cannot be determined — callers record a failed observation, never a
    guessed country.
    """
    egress_ip = fetch_egress_ip(
        endpoint.proxy_url(), echo_urls, timeout=timeout, transport=transport
    )
    lookup = geoip if geoip is not None else GeoIpLookup()
    try:
        country = lookup.country_code(egress_ip)
    except GeoIpUnavailableError as exc:
        raise EgressProbeError(exc.code, str(exc)) from None
    if not country:
        raise EgressProbeError(
            "geoip_lookup_failed", "GeoIP database has no country for the egress IP"
        )
    return egress_ip, country
