"""Egress probe runners (t052, rebuilt in t094).

t094 removes the container sandbox: the probe now runs in the API process
through an explicit proxy (``trust_env=False`` + an explicit ``proxy=`` so
there is no direct egress fallback), allowlisted echo endpoints and local
GeoIP. ``LocalEgressProbeRunner`` remains a deterministic, injectable
runner for tests; ``InProcessEgressProbeRunner`` is the production runner.
No Supervisor RPC, helper container, dedicated bridge or policy-agent is
involved any more.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from cbrowser.shared.egress import (
    ECHO_URLS,
    EgressProbeError,
    GeoIpLookup,
    probe_egress_detail,
)
from cbrowser.domain.proxy_endpoint import (
    ProxyEndpoint,
    map_endpoint_for_container,
)

logger = logging.getLogger("cbrowser.services.egress_probe")


@dataclass(frozen=True)
class EgressProbeResult:
    egress_ip: str
    country_code: str | None
    country_name: str | None = None
    city: str | None = None
    latency_ms: int | None = None
    source: str = "local_geoip"


class EgressProbeRunner(Protocol):
    async def probe(
        self, proxy_id: str, endpoint: ProxyEndpoint, credential_revision: int
    ) -> EgressProbeResult: ...


class LocalEgressProbeRunner:
    """Deterministic injectable runner for tests (no real network)."""

    def __init__(
        self,
        geoip: GeoIpLookup | None = None,
        echo_urls: tuple[str, ...] | list[str] | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._geoip = geoip
        self._echo_urls = echo_urls
        self._transport = transport
        self._timeout = timeout

    async def probe(
        self, proxy_id: str, endpoint: ProxyEndpoint, credential_revision: int
    ) -> EgressProbeResult:
        kwargs: dict = {"timeout": self._timeout, "transport": self._transport}
        if self._echo_urls is not None:
            kwargs["echo_urls"] = self._echo_urls
        if self._geoip is not None:
            kwargs["geoip"] = self._geoip
        detail = probe_egress_detail(endpoint.proxy_url(), **kwargs)
        return EgressProbeResult(
            egress_ip=detail.egress_ip,
            country_code=detail.country_code,
            country_name=detail.country_name,
            city=detail.city,
            latency_ms=detail.latency_ms,
            source=detail.source,
        )


class InProcessEgressProbeRunner:
    """Production egress probe (t094): in-process, explicit-proxy only.

    The endpoint URL always carries an explicit ``proxy=`` with
    ``trust_env=False`` inside :func:`probe_egress_detail`, so a failed or
    malformed proxy can never fall back to the API process's own egress.
    Echo targets are the fixed allowlist in ``ECHO_URLS``; private/reserved
    echo addresses are never contacted. No container/network is created,
    so there is no churn and no sandbox to tear down.

    ``geoip`` is a required construction-time dependency (t096 AC-002):
    the caller resolves and injects it, so probe I/O never consults hidden
    environment variables to locate the mmdb.
    """

    def __init__(
        self,
        *,
        geoip: GeoIpLookup,
        timeout: float = 10.0,
        echo_urls: tuple[str, ...] = ECHO_URLS,
        map_loopback: bool = True,
    ) -> None:
        self._timeout = timeout
        self._echo_urls = echo_urls
        self._geoip = geoip
        self._map_loopback = map_loopback

    def is_enabled(self) -> bool:
        # Always available: no external Supervisor dependency.
        return True

    async def probe(
        self, proxy_id: str, endpoint: ProxyEndpoint, credential_revision: int
    ) -> EgressProbeResult:
        # A loopback proxy stored as 127.0.0.1 must be rewritten to the
        # host-gateway hostname: the API runs inside a compose container
        # where 127.0.0.1 is the container itself, not the host (t094 AC-002).
        # The stored endpoint keeps its loopback host for fingerprint
        # stability; only the runtime probe endpoint is mapped.
        probe_endpoint = (
            map_endpoint_for_container(endpoint)
            if self._map_loopback and getattr(endpoint, "is_loopback", False)
            else endpoint
        )
        proxy_url = probe_endpoint.proxy_url()
        if not proxy_url:
            raise EgressProbeError(
                "proxy_unavailable", "no proxy endpoint configured for probe"
            )
        # The echo HTTP exchange is blocking I/O. Run it off the event loop
        # so probe waiting never starves SSE progress or ordinary API calls
        # (t094 AC-005). The timeout budget is passed into the HTTP client.
        detail = await asyncio.to_thread(
            probe_egress_detail,
            proxy_url,
            echo_urls=self._echo_urls,
            geoip=self._geoip,
            timeout=self._timeout,
        )
        return EgressProbeResult(
            egress_ip=detail.egress_ip,
            country_code=detail.country_code,
            country_name=detail.country_name,
            city=detail.city,
            latency_ms=detail.latency_ms,
            source=detail.source,
        )
