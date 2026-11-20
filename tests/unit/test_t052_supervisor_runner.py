"""t094: in-process egress probe runners (the container sandbox is retired).

The production runner lives in ``services.egress_probe`` and probes through
an explicit ``proxy=`` with ``trust_env=False``.  ``LocalEgressProbeRunner``
stays injectable for tests.  Everything here uses ``httpx.MockTransport``
or a stubbed probe function — no Supervisor, no Docker, no real network.
"""

from __future__ import annotations

import threading
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
)


def _endpoint(scheme: str = "http") -> ProxyEndpoint:
    return ProxyEndpoint(
        scheme=scheme,
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
        latency_ms=42,
        source="local_geoip",
    )


class _StubGeoIp:
    def location(self, ip: str) -> GeoLocation:
        return GeoLocation(country_code="JP", country_name="Japan", city="Tokyo")


@pytest.mark.asyncio
async def test_in_process_runner_passes_explicit_proxy_and_maps_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict = {}

    def fake_detail(proxy_url: str, **kwargs: object) -> EgressProbeDetail:
        called["proxy_url"] = proxy_url
        called["kwargs"] = kwargs
        return _detail()

    monkeypatch.setattr(runner_mod, "probe_egress_detail", fake_detail)
    result = await InProcessEgressProbeRunner().probe("px-1", _endpoint(), 3)

    assert result == EgressProbeResult(
        egress_ip="203.0.113.7",
        country_code="JP",
        country_name="Japan",
        city="Tokyo",
        latency_ms=42,
        source="local_geoip",
    )
    assert called["proxy_url"] == "http://user:s3cret-pw@proxy.example.com:8080"
    assert "transport" not in called["kwargs"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", ["http", "https", "socks5"])
async def test_in_process_runner_supports_all_three_schemes_without_downgrade(
    monkeypatch: pytest.MonkeyPatch, scheme: str
) -> None:
    """http/https/socks5 proxies are all passed through to the probe; no
    scheme is silently downgraded or dropped (t094 AC-002)."""
    called: dict = {}

    def fake_detail(proxy_url: str, **kwargs: object) -> EgressProbeDetail:
        called["proxy_url"] = proxy_url
        return _detail()

    monkeypatch.setattr(runner_mod, "probe_egress_detail", fake_detail)
    await InProcessEgressProbeRunner().probe("px-1", _endpoint(scheme), 1)
    assert called["proxy_url"].startswith(f"{scheme}://")


@pytest.mark.asyncio
async def test_in_process_runner_maps_loopback_proxy_to_host_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stored loopback proxy must be rewritten to host.docker.internal so
    the in-process API container can actually reach it (t094 AC-002)."""
    called: dict = {}

    def fake_detail(proxy_url: str, **kwargs: object) -> EgressProbeDetail:
        called["proxy_url"] = proxy_url
        return _detail()

    monkeypatch.setattr(runner_mod, "probe_egress_detail", fake_detail)
    loopback = ProxyEndpoint(
        scheme="http", host="127.0.0.1", port=21001,
        username="user", password="pw",
    )
    result = await InProcessEgressProbeRunner().probe("px-1", loopback, 1)
    assert result.egress_ip == "203.0.113.7"
    assert called["proxy_url"] == "http://user:pw@host.docker.internal:21001"


@pytest.mark.asyncio
async def test_in_process_runner_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The blocking echo HTTP exchange runs off the event loop so SSE
    progress and ordinary API requests keep flowing during a probe (t094
    AC-005)."""
    import asyncio

    main_thread = threading.get_ident()
    probe_threads: list[int] = []

    def fake_detail(proxy_url: str, **kwargs: object) -> EgressProbeDetail:
        probe_threads.append(threading.get_ident())
        return _detail()

    monkeypatch.setattr(runner_mod, "probe_egress_detail", fake_detail)
    await InProcessEgressProbeRunner().probe("px-1", _endpoint(), 1)
    assert probe_threads
    assert all(tid != main_thread for tid in probe_threads)


@pytest.mark.asyncio
async def test_in_process_runner_never_falls_back_to_direct_egress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail_calls: list = []
    clients: list = []

    def fake_detail(*_a: object, **_k: object) -> None:
        detail_calls.append(1)
        raise EgressProbeError("echo_unreachable", "echo down")

    def spy_client(*_a: object, **_k: object) -> None:
        clients.append(1)
        raise AssertionError("no direct httpx.Client may be built by the runner")

    monkeypatch.setattr(runner_mod, "probe_egress_detail", fake_detail)
    monkeypatch.setattr(httpx, "Client", spy_client)

    with pytest.raises(EgressProbeError) as exc:
        await InProcessEgressProbeRunner().probe("px-1", _endpoint(), 3)
    assert exc.value.code == "echo_unreachable"
    assert detail_calls == [1]
    assert clients == []


@pytest.mark.asyncio
async def test_in_process_runner_rejects_missing_proxy_without_direct_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner_mod,
        "probe_egress_detail",
        lambda *_a, **_k: pytest.fail("no probe may run without a proxy"),
    )
    endpoint = SimpleNamespace(proxy_url=lambda: None)
    with pytest.raises(EgressProbeError) as exc:
        await InProcessEgressProbeRunner().probe("px-1", endpoint, 1)
    assert exc.value.code == "proxy_unavailable"


def test_in_process_runner_is_always_enabled() -> None:
    assert InProcessEgressProbeRunner().is_enabled() is True


@pytest.mark.asyncio
async def test_in_process_runner_propagates_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise EgressProbeError("geoip_db_missing", "no GeoIP database")

    monkeypatch.setattr(runner_mod, "probe_egress_detail", boom)
    with pytest.raises(EgressProbeError) as exc:
        await InProcessEgressProbeRunner().probe("px-1", _endpoint(), 1)
    assert exc.value.code == "geoip_db_missing"


@pytest.mark.parametrize("scheme", ["http", "https", "socks5"])
@pytest.mark.asyncio
async def test_proxy_url_shape_for_supported_schemes(
    scheme: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def fake_detail(proxy_url: str, **_k: object) -> EgressProbeDetail:
        captured["proxy_url"] = proxy_url
        return _detail()

    monkeypatch.setattr(runner_mod, "probe_egress_detail", fake_detail)
    await InProcessEgressProbeRunner().probe("px-1", _endpoint(scheme), 1)
    assert captured["proxy_url"] == (
        f"{scheme}://user:s3cret-pw@proxy.example.com:8080"
    )


def test_fetch_egress_ip_passes_explicit_proxy_and_disables_trust_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    real_client = httpx.Client

    def _echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="203.0.113.7\n")

    def spy_client(*_a: object, **kwargs: object) -> httpx.Client:
        captured.update(kwargs)
        return real_client(transport=httpx.MockTransport(_echo))

    monkeypatch.setattr(httpx, "Client", spy_client)
    ip = fetch_egress_ip(
        "http://user:pw@proxy.example.com:8080",
        echo_urls=("https://echo.example/ip",),
    )
    assert ip == "203.0.113.7"
    assert captured["proxy"] == "http://user:pw@proxy.example.com:8080"
    assert captured["trust_env"] is False


@pytest.mark.asyncio
async def test_local_runner_injects_transport_and_geoip_and_maps_result() -> None:
    def _echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="203.0.113.7\n")

    runner = LocalEgressProbeRunner(
        echo_urls=("https://echo.example/ip",),
        transport=httpx.MockTransport(_echo),
        geoip=_StubGeoIp(),
    )
    result = await runner.probe("px-1", SimpleNamespace(proxy_url=lambda: None), 1)
    assert result.egress_ip == "203.0.113.7"
    assert result.country_code == "JP"
    assert result.country_name == "Japan"
    assert result.city == "Tokyo"
    assert result.source == "local_geoip"
    assert result.latency_ms is not None and result.latency_ms >= 1


@pytest.mark.asyncio
async def test_local_runner_uses_only_configured_echo_urls() -> None:
    seen: list[str] = []

    def _echo(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text="203.0.113.7\n")

    runner = LocalEgressProbeRunner(
        echo_urls=("https://echo-1.example/ip", "https://echo-2.example/ip"),
        transport=httpx.MockTransport(_echo),
        geoip=_StubGeoIp(),
    )
    result = await runner.probe("px-1", SimpleNamespace(proxy_url=lambda: None), 1)
    assert result.egress_ip == "203.0.113.7"
    assert seen == ["https://echo-1.example/ip"]


@pytest.mark.asyncio
async def test_local_runner_propagates_probe_error() -> None:
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    runner = LocalEgressProbeRunner(
        echo_urls=("https://echo.example/ip",),
        transport=httpx.MockTransport(_boom),
        geoip=_StubGeoIp(),
    )
    with pytest.raises(EgressProbeError) as exc:
        await runner.probe("px-1", SimpleNamespace(proxy_url=lambda: None), 1)
    assert exc.value.code == "echo_unreachable"
