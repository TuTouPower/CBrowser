"""Egress probe runners (t052).

The probe must run in the Supervisor's helper container — the only place
that shares the Browser's network policy and proxy parameters (the API
process has a different egress path, so probing there would observe the
wrong exit).  The production runner is :class:`SupervisorEgressProbeRunner`
(API -> Supervisor control API -> Docker helper).  :class:`LocalEgressProbeRunner`
runs the same echo+GeoIP logic in-process and exists only for tests: it
must never be wired into the production app.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx

from cbrowser.shared.egress import EgressProbeError, GeoIpLookup, probe_egress
from cbrowser.domain.proxy_endpoint import ProxyEndpoint

logger = logging.getLogger("cbrowser.services.egress_probe")


@dataclass(frozen=True)
class EgressProbeResult:
    egress_ip: str
    country_code: str | None


class EgressProbeRunner(Protocol):
    async def probe(
        self, proxy_id: str, endpoint: ProxyEndpoint, credential_revision: int
    ) -> EgressProbeResult: ...


class LocalEgressProbeRunner:
    """In-process probe (tests only).

    Runs :func:`cbrowser.shared.egress.probe_egress` in this
    process.  Correct for logic tests with controlled echo/proxy fixtures,
    wrong for production: this process does not share the Browser network
    perspective, so its egress IP is not the Browser's.
    """

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
        egress_ip, country = probe_egress(endpoint.proxy_url(), **kwargs)
        return EgressProbeResult(egress_ip=egress_ip, country_code=country)


class SupervisorEgressProbeRunner:
    """Production probe runner: ask the Supervisor control API to run the
    egress probe in its helper container (Browser network perspective).

    The endpoint credentials travel in the request body to the internal,
    token-authenticated control API only (localhost); they are never
    logged.  The public probe API accepts a proxy id alone and loads the
    stored credentials server-side.
    """

    def __init__(
        self,
        supervisor_url: str | None,
        supervisor_token: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 90.0,
    ) -> None:
        self._url = supervisor_url.strip().rstrip("/") if supervisor_url else None
        self._token = supervisor_token.strip() if supervisor_token else None
        self._transport = transport
        self._timeout = timeout

    def is_enabled(self) -> bool:
        return bool(self._url and self._token)

    async def probe(
        self, proxy_id: str, endpoint: ProxyEndpoint, credential_revision: int
    ) -> EgressProbeResult:
        if not self.is_enabled():
            raise EgressProbeError(
                "supervisor_unavailable",
                "Supervisor is not configured; egress probe cannot run",
            )
        url = f"{self._url}/supervisor/v1/proxies/{quote(proxy_id, safe='')}/probe"
        headers = {"Authorization": f"Bearer {self._token}"}
        body = {
            "scheme": endpoint.scheme,
            "host": endpoint.host,
            "port": endpoint.port,
            "username": endpoint.username,
            "password": endpoint.password,
            "credential_revision": credential_revision,
            "endpoint_fingerprint": endpoint.fingerprint,
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=self._timeout, trust_env=False
            ) as client:
                resp = await client.post(url, json=body, headers=headers)
        except Exception as exc:
            raise EgressProbeError(
                "supervisor_unavailable",
                f"Supervisor probe request failed: {type(exc).__name__}",
            ) from None
        if resp.status_code != 200:
            raise EgressProbeError(
                "supervisor_unavailable",
                f"Supervisor probe request failed: HTTP {resp.status_code}",
            )
        try:
            data = resp.json()
        except ValueError:
            raise EgressProbeError(
                "supervisor_unavailable", "Supervisor probe returned bad JSON"
            ) from None
        if not isinstance(data, dict):
            # A non-dict body (list, string, ...) must not leak an
            # AttributeError to the caller: the pending observation would
            # otherwise hang forever with no failed row and no diagnosis.
            raise EgressProbeError(
                "probe_bad_response",
                "Supervisor probe returned a non-object JSON body",
            )
        if data.get("status") != "ok" or not data.get("egress_ip"):
            raise EgressProbeError(
                data.get("error_code") or "probe_failed",
                "Supervisor probe failed",
            )
        return EgressProbeResult(
            egress_ip=data["egress_ip"], country_code=data.get("country_code")
        )
