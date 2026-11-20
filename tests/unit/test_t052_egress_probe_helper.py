"""t094: in-process egress probe core tests (the container sandbox is retired).

``runtime_agent.egress_probe`` no longer exists. These tests cover the
lightweight replacement instead: the runners in ``services.egress_probe``
and the pure probe functions in ``shared.egress`` they delegate to. No
container, bridge network, policy agent or helper executable is involved.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from cbrowser.domain.proxy_endpoint import ProxyEndpoint
from cbrowser.services import egress_probe as runner_mod
from cbrowser.services.egress_probe import (
    EgressProbeResult,
    InProcessEgressProbeRunner,
    LocalEgressProbeRunner,
)
from cbrowser.shared.egress import (
    EgressProbeDetail,
    EgressProbeError,
    GeoLocation,
    fetch_egress_ip,
    fetch_egress_ip_timed,
    probe_egress_detail,
)


def _endpoint() -> ProxyEndpoint:
    return ProxyEndpoint(
        scheme="http",
        host="proxy.example.com",
        port=8080,
        username="user",
        password="s3cret-pw",
    )


def _detail() -> EgressProbeDetail:
    return EgressProbeDetail(
        egress_ip="203.0.113.7",
        country_code="JP",
        country_name="Japan",
        city="Tokyo",
        latency_ms=128,
        source="local_geoip",
    )


class _StubGeoIp:
    def location(self, ip: str) -> GeoLocation:
        assert ip == "203.0.113.7"
        return GeoLocation(
            country_code="JP", country_name="Japan", city="Tokyo"
        )


@pytest.mark.asyncio
async def test_in_process_runner_maps_detail_without_any_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict = {}

    def fake_detail(proxy_url: str, **kwargs: object) -> EgressProbeDetail:
        called["proxy_url"] = proxy_url
        called["kwargs"] = kwargs
        return _detail()

    monkeypatch.setattr(runner_mod, "probe_egress_detail", fake_detail)
    runner = InProcessEgressProbeRunner()

    assert runner.is_enabled() is True
    result = await runner.probe("px-1", _endpoint(), 1)

    assert result == EgressProbeResult(
        egress_ip="203.0.113.7",
        country_code="JP",
        country_name="Japan",
        city="Tokyo",
        latency_ms=128,
        source="local_geoip",
    )
    assert "s3cret-pw" in called["proxy_url"]
    assert "transport" not in called["kwargs"]


@pytest.mark.asyncio
async def test_in_process_runner_propagates_probe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise EgressProbeError("echo_unreachable", "echo down")

    monkeypatch.setattr(runner_mod, "probe_egress_detail", boom)
    with pytest.raises(EgressProbeError) as exc:
        await InProcessEgressProbeRunner().probe("px-1", _endpoint(), 1)
    assert exc.value.code == "echo_unreachable"


@pytest.mark.asyncio
async def test_in_process_runner_rejects_missing_proxy_url() -> None:
    endpoint = SimpleNamespace(proxy_url=lambda: None)
    with pytest.raises(EgressProbeError) as exc:
        await InProcessEgressProbeRunner().probe("px-1", endpoint, 1)
    assert exc.value.code == "proxy_unavailable"


@pytest.mark.asyncio
async def test_local_runner_uses_injected_transport_and_geoip() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://echo.example/ip"
        return httpx.Response(200, text="203.0.113.7\n")

    runner = LocalEgressProbeRunner(
        echo_urls=("https://echo.example/ip",),
        transport=httpx.MockTransport(handler),
        geoip=_StubGeoIp(),
    )
    result = await runner.probe(
        "px-1", SimpleNamespace(proxy_url=lambda: None), 1
    )
    assert result.egress_ip == "203.0.113.7"
    assert result.country_code == "JP"
    assert result.city == "Tokyo"


def test_fetch_egress_ip_parses_first_valid_echo_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="203.0.113.7\n")

    ip = fetch_egress_ip(
        None,
        echo_urls=("https://echo.example/ip",),
        transport=httpx.MockTransport(handler),
    )
    assert ip == "203.0.113.7"


def test_fetch_egress_ip_timed_reports_positive_latency() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="203.0.113.7")

    ip, latency_ms = fetch_egress_ip_timed(
        None,
        echo_urls=("https://echo.example/ip",),
        transport=httpx.MockTransport(handler),
    )
    assert ip == "203.0.113.7"
    assert isinstance(latency_ms, int) and latency_ms >= 1


def test_probe_egress_detail_uses_local_geoip_without_services() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="203.0.113.7")

    detail = probe_egress_detail(
        None,
        echo_urls=("https://echo.example/ip",),
        geoip=_StubGeoIp(),
        transport=httpx.MockTransport(handler),
        geo_service_urls=(),
    )
    assert detail.egress_ip == "203.0.113.7"
    assert detail.country_code == "JP"
    assert detail.country_name == "Japan"
    assert detail.city == "Tokyo"
    assert detail.source == "local_geoip"
