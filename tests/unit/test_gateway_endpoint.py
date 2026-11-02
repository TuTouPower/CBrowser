"""Gateway endpoint is the single port source; Origin normalization is shared."""

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.gateway.endpoint import (
    DEFAULT_GATEWAY_PORT,
    GatewayEndpoint,
    normalize_origin,
    normalize_origins,
)
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


def test_default_gateway_endpoint_is_18080() -> None:
    endpoint = GatewayEndpoint()
    assert DEFAULT_GATEWAY_PORT == 18080
    assert endpoint.port == 18080
    assert endpoint.ws_url == "ws://host.docker.internal:18080"
    assert GatewayEndpoint.from_url(endpoint.ws_url) == endpoint


def test_origin_normalization_ignores_trailing_slash_and_default_port() -> None:
    assert normalize_origin("https://app.example.com/") == "https://app.example.com"
    assert normalize_origin("https://app.example.com:443") == "https://app.example.com"
    assert normalize_origin("http://localhost:3000/") == "http://localhost:3000"
    assert normalize_origin("http://example.com:80/") == "http://example.com"
    assert normalize_origins(
        "https://app.example.com/, http://localhost:3000,https://app.example.com"
    ) == ["https://app.example.com", "http://localhost:3000"]
    with pytest.raises(ValueError):
        normalize_origin("not-an-origin")
    with pytest.raises(ValueError):
        normalize_origin("https://app.example.com/path")


@pytest.mark.asyncio
async def test_supervisor_rejects_gateway_url_port_mismatch(tmp_path: Path) -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:1", trust_env=False) as api:
        with pytest.raises(ValueError, match="does not match"):
            SupervisorCore(
                SimpleNamespace(validator=PathValidator(tmp_path)),
                PortAllocator(),
                EventForwarder(
                    str(tmp_path / "unused"), tmp_path / "spool", client=api
                ),
                api,
                gateway_url="ws://host.docker.internal:18097",
                gateway_port=18080,
            )
