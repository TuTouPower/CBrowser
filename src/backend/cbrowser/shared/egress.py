"""Egress probe I/O: echo fetch + local GeoIP lookup (t052, t062, t074).

Neutral home: the probe runs in the API process, in the Supervisor's
helper flow and inside the Browser image, so it cannot live in any
one service package (t062).

The egress IP is discovered by asking an IP-echo endpoint *through the
proxy* (never directly from the API process, whose egress may differ
from the Browser's). Country and city are resolved from the egress IP
against the local GeoLite2 database; an allowlisted read-only HTTPS GeoIP
service may supply a missing city, but the local database is the primary
source (t074 / d048: online services are unreliable and rate-limited).

It is I/O, not domain logic: it performs HTTP through ``httpx``,
reads the GeoIP database file and resolves paths from the environment.
The pure observation value object and validity rules live in
``cbrowser.domain.egress_observation``. This module imports no other
cbrowser module at all, so every image that ships the shared package
can import it.

``geoip2`` is imported lazily: the API/Supervisor images do not ship
it, only the Browser image does (``cloakbrowser[geoip]``).
"""

from __future__ import annotations

import ipaddress
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

GEOIP_DB_FILENAME = "GeoLite2-City.mmdb"

#: Plain-text IP echo services (same set as the CloakBrowser SDK).
ECHO_URLS: tuple[str, ...] = (
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ifconfig.me/ip",
)

#: Allowlisted read-only HTTPS GeoIP services, in fallback order (t074).
#: Only queried when the local database cannot supply a city; every failure
#: (TLS, 429, redirect, missing field) falls back to the local database.
GEO_SERVICE_URLS: tuple[str, ...] = (
    "https://freeipapi.com/api/json",
    "https://ipwho.is/",
    "https://api.ip.sb/geoip",
)


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

    A missing database or reader is a hard failure
    (``GeoIpUnavailableError``) — the observation is recorded as failed,
    never guessed.
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

    def location(self, ip: str) -> GeoLocation:
        """Full country/city lookup reading ``country.names`` and
        ``city.names`` (t074 / p106): the old lookup discarded both."""
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
                name = response.country.name
                city = response.city.name
        except Exception as exc:
            raise GeoIpUnavailableError(
                "geoip_lookup_failed",
                f"GeoIP lookup failed: {type(exc).__name__}",
            ) from None
        return GeoLocation(
            country_code=code.upper() if code else None,
            country_name=name if name else None,
            city=city if city else None,
        )


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
    proxy_url: str | None,
    echo_urls: tuple[str, ...] | list[str] = ECHO_URLS,
    geoip: GeoIpLookup | None = None,
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str | None]:
    """Probe one proxy: egress IP through it, then local country.

    ``proxy_url`` is the endpoint's full URL (with credentials), as
    produced by ``ProxyEndpoint.proxy_url()``; ``None`` probes the
    caller's own egress (tests / API-egress control only). Returns
    ``(egress_ip, country_code)``. Raises :class:`EgressProbeError`
    (``geoip_db_missing`` etc.) when the country cannot be determined —
    callers record a failed observation, never a guessed country.
    """
    egress_ip = fetch_egress_ip(
        proxy_url, echo_urls, timeout=timeout, transport=transport
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


@dataclass(frozen=True)
class GeoLocation:
    """Country/city resolved from the local GeoLite2 database."""

    country_code: str | None
    country_name: str | None
    city: str | None


@dataclass(frozen=True)
class EgressProbeDetail:
    """Full observation from one probe (t074).

    ``latency_ms`` is only the real network round-trip of the probe HTTP
    request through the proxy — never container/network/policy setup or
    teardown. ``source`` records whether the city came from the local
    database or an allowlisted online service.
    """

    egress_ip: str
    country_code: str | None
    country_name: str | None
    city: str | None
    latency_ms: int
    source: str


def _geo_service_location(
    client: httpx.Client, url: str
) -> tuple[str | None, str | None] | None:
    """Optional online city/name supplement; never a hard dependency."""
    try:
        resp = client.get(url, follow_redirects=True)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("ip"), str) and not isinstance(
        data.get("ipAddress"), str
    ):
        return None
    city = data.get("cityName") or data.get("city")
    name = data.get("countryName") or data.get("country")
    if not isinstance(city, str) or not city:
        return None
    return (
        name if isinstance(name, str) else None,
        city,
    )


def fetch_egress_ip_timed(
    proxy_url: str | None,
    echo_urls: tuple[str, ...] | list[str] = ECHO_URLS,
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, int]:
    """IP echo plus the real network RTT in milliseconds (t074).

    ``time.monotonic()`` wraps only the probe HTTP exchange through the
    proxy; container/network/policy lifecycle is never included.
    """
    started = time.monotonic()
    egress_ip = fetch_egress_ip(
        proxy_url, echo_urls, timeout=timeout, transport=transport
    )
    latency_ms = max(1, round((time.monotonic() - started) * 1000))
    return egress_ip, latency_ms


def probe_egress_detail(
    proxy_url: str | None,
    echo_urls: tuple[str, ...] | list[str] = ECHO_URLS,
    geoip: GeoIpLookup | None = None,
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
    geo_service_urls: tuple[str, ...] | list[str] = GEO_SERVICE_URLS,
) -> EgressProbeDetail:
    """Full probe: timed IP echo + local mmdb country/city, with an
    optional online city supplement (d048: online services are unreliable
    and rate-limited, so the local database is always the primary source).
    """
    egress_ip, latency_ms = fetch_egress_ip_timed(
        proxy_url, echo_urls, timeout=timeout, transport=transport
    )
    lookup = geoip if geoip is not None else GeoIpLookup()
    try:
        location = lookup.location(egress_ip)
    except GeoIpUnavailableError as exc:
        raise EgressProbeError(exc.code, str(exc)) from None
    if not location.country_code:
        raise EgressProbeError(
            "geoip_lookup_failed", "GeoIP database has no country for the egress IP"
        )
    country_name = location.country_name
    city = location.city
    source = "local_geoip"
    if not city and geo_service_urls and transport is None:
        # A separate short-lived client: never reuse the echo connection
        # pool across a different service (d049). Online services are
        # best-effort; any failure falls back to the local result.
        try:
            with httpx.Client(
                proxy=proxy_url or None,
                timeout=timeout,
                trust_env=False,
            ) as client:
                for url in geo_service_urls:
                    online = _geo_service_location(client, url)
                    if online is not None:
                        country_name = online[0] or country_name
                        city = online[1]
                        source = "geo_service"
                        break
        except httpx.HTTPError:
            pass
    return EgressProbeDetail(
        egress_ip=egress_ip,
        country_code=location.country_code,
        country_name=country_name,
        city=city,
        latency_ms=latency_ms,
        source=source,
    )
