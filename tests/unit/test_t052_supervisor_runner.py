"""t052: SupervisorEgressProbeRunner unit tests (test f004).

The production probe runner (API -> Supervisor control API -> Docker
helper) had zero tests; only the test-only LocalEgressProbeRunner was
covered.  These use httpx.MockTransport — no Supervisor, no Docker.
"""

from __future__ import annotations

import json

import httpx
import pytest

from cbrowser.domain.egress_observation import EgressProbeError
from cbrowser.domain.proxy_endpoint import ProxyEndpoint
from cbrowser.services.egress_probe import SupervisorEgressProbeRunner

ENDPOINT = ProxyEndpoint(
    scheme="http",
    host="proxy.example.com",
    port=8080,
    username="user",
    password="s3cret-pw",
)


def _runner(handler, url="http://supervisor:9000", token="tok-123"):
    transport = httpx.MockTransport(handler)
    return SupervisorEgressProbeRunner(url, token, transport=transport)


def _ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/supervisor/v1/proxies/px-1/probe"
    assert request.headers["Authorization"] == "Bearer tok-123"
    body = json.loads(request.content)
    # Credentials travel in the body to the internal control API only.
    assert body["password"] == "s3cret-pw"
    assert body["endpoint_fingerprint"] == ENDPOINT.fingerprint
    assert body["credential_revision"] == 3
    return httpx.Response(
        200, json={"status": "ok", "egress_ip": "203.0.113.7", "country_code": "JP"}
    )


@pytest.mark.asyncio
async def test_probe_success_returns_egress_ip_and_country():
    result = await _runner(_ok_handler).probe("px-1", ENDPOINT, 3)
    assert result.egress_ip == "203.0.113.7"
    assert result.country_code == "JP"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 500, 502])
async def test_probe_non_200_is_supervisor_unavailable(status):
    runner = _runner(lambda request: httpx.Response(status, json={"status": "failed"}))

    with pytest.raises(EgressProbeError) as excinfo:
        await runner.probe("px-1", ENDPOINT, 3)
    assert excinfo.value.code == "supervisor_unavailable"


@pytest.mark.asyncio
async def test_probe_bad_json_is_supervisor_unavailable():
    runner = _runner(lambda request: httpx.Response(200, content=b"not-json{"))

    with pytest.raises(EgressProbeError) as excinfo:
        await runner.probe("px-1", ENDPOINT, 3)
    assert excinfo.value.code == "supervisor_unavailable"


@pytest.mark.asyncio
async def test_probe_non_dict_json_is_controlled_failure_not_attribute_error():
    """code f002 (red before fix): a non-dict JSON body must not raise
    AttributeError out of the runner — it is a controlled probe failure
    with a machine-readable code, so the service can record a failed
    observation instead of leaving the pending row hanging."""
    runner = _runner(lambda request: httpx.Response(200, json=["not", "a", "dict"]))

    with pytest.raises(EgressProbeError) as excinfo:
        await runner.probe("px-1", ENDPOINT, 3)
    assert excinfo.value.code == "probe_bad_response"


@pytest.mark.asyncio
async def test_probe_failed_status_passes_through_error_code():
    runner = _runner(
        lambda request: httpx.Response(
            200, json={"status": "failed", "error_code": "geoip_db_missing"}
        )
    )

    with pytest.raises(EgressProbeError) as excinfo:
        await runner.probe("px-1", ENDPOINT, 3)
    assert excinfo.value.code == "geoip_db_missing"


@pytest.mark.asyncio
async def test_probe_ok_without_egress_ip_is_probe_failed():
    runner = _runner(
        lambda request: httpx.Response(
            200, json={"status": "ok", "country_code": "JP"}
        )
    )

    with pytest.raises(EgressProbeError) as excinfo:
        await runner.probe("px-1", ENDPOINT, 3)
    assert excinfo.value.code == "probe_failed"


@pytest.mark.asyncio
async def test_probe_unconfigured_supervisor_is_unavailable():
    runner = SupervisorEgressProbeRunner(None, None)
    assert runner.is_enabled() is False

    with pytest.raises(EgressProbeError) as excinfo:
        await runner.probe("px-1", ENDPOINT, 3)
    assert excinfo.value.code == "supervisor_unavailable"


@pytest.mark.asyncio
async def test_probe_transport_error_is_supervisor_unavailable():
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(EgressProbeError) as excinfo:
        await _runner(_boom).probe("px-1", ENDPOINT, 3)
    assert excinfo.value.code == "supervisor_unavailable"
