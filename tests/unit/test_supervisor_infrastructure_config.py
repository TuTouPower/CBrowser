"""Unit tests for Supervisor infrastructure configuration (gateway only).

Covers:
1. SupervisorCore gateway configuration combinations.
2. start_profile works without a gateway container and uses the configured URL.
3. attach_profile_infrastructure connects the gateway and returns its address.
4. Stream gateway_url selection: configured URL vs media-network gateway URL.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


def test_supervisor_core_allows_gateway_none_or_set(tmp_path: Path):
    validator = PathValidator(tmp_path)
    adapter = SimpleNamespace(validator=validator)
    ports = PortAllocator()
    events = MagicMock(spec=EventForwarder)
    api = MagicMock(spec=httpx.AsyncClient)
    key_file = tmp_path / "agent_key"
    key_file.write_text(secrets.token_urlsafe(32))
    key_file.chmod(0o600)

    core_none = SupervisorCore(
        docker_adapter=adapter,
        port_allocator=ports,
        event_forwarder=events,
        api_client=api,
        agent_key_file=key_file,
        gateway_container_id=None,
    )
    assert core_none.gateway_container_id is None
    assert not hasattr(core_none, "coturn_container_id")

    core_set = SupervisorCore(
        docker_adapter=adapter,
        port_allocator=ports,
        event_forwarder=events,
        api_client=api,
        agent_key_file=key_file,
        gateway_container_id="gw_c1",
    )
    assert core_set.gateway_container_id == "gw_c1"


def test_attach_profile_infrastructure_connects_gateway_only(tmp_path: Path):
    validator = PathValidator(tmp_path)
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "geoip").mkdir()
    client = MagicMock()
    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine_dir,
        docker_client=client,
        browser_image="sha256:" + "a" * 64,
        stream_image="sha256:" + "b" * 64,
        resource_prefix="t006-unit",
        deployment_instance_id="dep-infra",
    )

    mock_net = MagicMock()
    mock_net.name = "t006-unit-net-prof1"
    mock_net.attrs = {
        "Labels": {
            "com.cbrowser.prefix": "t006-unit",
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.instance-id": "dep-infra",
            "com.cbrowser.profile-id": "prof1",
        },
        "Containers": {},
    }
    mock_net.reload = MagicMock()
    mock_net.connect = MagicMock()
    client.networks.get.return_value = mock_net

    mock_gateway = MagicMock()
    mock_gateway.id = "gateway_id_123"
    mock_gateway.status = "running"
    mock_gateway.labels = {
        "com.cbrowser.prefix": "t006-unit",
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "gateway",
    }
    mock_gateway.attrs = {
        "NetworkSettings": {
            "Networks": {"t006-unit-net-prof1": {"IPAddress": "10.42.0.3"}}
        }
    }
    client.containers.get.return_value = mock_gateway

    result = adapter.attach_profile_infrastructure(
        profile_id="prof1",
        gateway_container_id="gateway_id_123",
    )

    assert result["gateway_ip"] == "10.42.0.3"
    assert result["gateway_url"] == "ws://10.42.0.3:18080"
    mock_net.connect.assert_called_once_with(mock_gateway)


@pytest.mark.asyncio
async def test_start_profile_stream_gateway_url_selection(tmp_path: Path):
    validator = PathValidator(tmp_path)
    dirs = {
        key: tmp_path / key
        for key in ("runtime", "profile", "events", "exchange", "x11", "pulse")
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    info_path = dirs["runtime"] / "runner_info.json"
    (dirs["runtime"] / "x11").mkdir(exist_ok=True)
    (dirs["runtime"] / "x11" / "X99").touch()
    (dirs["runtime"] / "pulse").mkdir(exist_ok=True)
    (dirs["runtime"] / "pulse" / "pulse.sock").touch()
    (dirs["runtime"] / "Xauthority").touch()
    (dirs["runtime"] / "agent.sock").touch()

    key_file = tmp_path / "agent_key"
    key_file.write_text(secrets.token_urlsafe(32))
    key_file.chmod(0o600)

    mock_browser_container = MagicMock()
    mock_browser_container.id = "b_cid"
    mock_browser_container.name = "t006-unit-browser-prof_test"
    mock_stream_container = MagicMock()
    mock_stream_container.id = "s_cid"
    mock_stream_container.status = "running"
    mock_stream_container.reload = MagicMock()

    mock_gateway_control = MagicMock()
    mock_gateway_control.has_foreground_viewers = AsyncMock(return_value=False)

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/runtime"):
            return httpx.Response(
                200,
                json={
                    "desired_state": "running",
                    "restart_blocked": False,
                    "runtime_instance_id": None,
                    "config_version": 1,
                    "observed_state": "stopped",
                },
            )
        if request.url.path.endswith("/bind"):
            return httpx.Response(200, json={"status": "bound"})
        if request.url.path.endswith("/observed"):
            return httpx.Response(200, json={"status": "observed"})
        return httpx.Response(404)

    def write_runner_info(profile_id, runtime_instance_id, snapshot_json_path):
        info_path.write_text(
            json.dumps(
                {
                    "profile_id": profile_id,
                    "runtime_instance_id": runtime_instance_id,
                    "config_version": 1,
                    "browser_pid": 12345,
                }
            )
        )
        return mock_browser_container

    transport = httpx.MockTransport(mock_handler)

    # Case A: no gateway container -> configured Supervisor URL is used.
    adapter_plain = SimpleNamespace(
        validator=validator,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        attach_profile_infrastructure=MagicMock(),
        start_browser_container=AsyncMock(side_effect=write_runner_info),
        start_stream_container=AsyncMock(return_value=mock_stream_container),
        teardown_profile=AsyncMock(),
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test-api"
    ) as api:
        core = SupervisorCore(
            docker_adapter=adapter_plain,
            port_allocator=PortAllocator(30000, 30010),
            event_forwarder=MagicMock(spec=EventForwarder),
            api_client=api,
            gateway_url="ws://supervisor-host-gw:18080",
            token_file=None,
            agent_key_file=key_file,
            gateway_control=mock_gateway_control,
            gateway_container_id=None,
        )
        session = await core.start_profile("prof_test", ProfileConfig(name="test"))
        assert session.observed_state == "running"
        adapter_plain.attach_profile_infrastructure.assert_not_called()
        call_kwargs = adapter_plain.start_stream_container.call_args.kwargs
        assert call_kwargs["gateway_url"] == "ws://supervisor-host-gw:18080"
        assert "media_addresses" not in call_kwargs

    # Case B: gateway container attached -> media network URL wins.
    adapter_paired = SimpleNamespace(
        validator=validator,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        attach_profile_infrastructure=MagicMock(
            return_value={
                "gateway_ip": "10.42.0.3",
                "gateway_url": "ws://10.42.0.3:18080",
            }
        ),
        start_browser_container=AsyncMock(side_effect=write_runner_info),
        start_stream_container=AsyncMock(return_value=mock_stream_container),
        teardown_profile=AsyncMock(),
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test-api"
    ) as api:
        core_paired = SupervisorCore(
            docker_adapter=adapter_paired,
            port_allocator=PortAllocator(30000, 30010),
            event_forwarder=MagicMock(spec=EventForwarder),
            api_client=api,
            gateway_url="ws://supervisor-host-gw:18080",
            token_file=None,
            agent_key_file=key_file,
            gateway_control=mock_gateway_control,
            gateway_container_id="gw_paired_id",
        )
        session2 = await core_paired.start_profile(
            "prof_test2", ProfileConfig(name="test2")
        )
        assert session2.observed_state == "running"

    adapter_paired.attach_profile_infrastructure.assert_called_once_with(
        "prof_test2", "gw_paired_id", gateway_port=18080
    )
    call_kwargs2 = adapter_paired.start_stream_container.call_args.kwargs
    assert call_kwargs2["gateway_url"] == "ws://10.42.0.3:18080"
