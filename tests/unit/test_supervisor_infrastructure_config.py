"""Unit tests for Supervisor infrastructure configuration (ADR 010 / t006).

Covers:
1. SupervisorCore configuration combinations: paired, coturn only, neither.
2. start_profile fail-closed before container creation when coturn is missing,
   reporting failure through existing event emission path.
3. attach_profile_infrastructure with gateway=None (coturn only) vs paired.
4. Stream gateway_url selection: SupervisorCore.gateway_url for coturn-only vs
   media network gateway_url for paired infrastructure.
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
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


def test_supervisor_core_allows_coturn_alone_and_paired_and_neither(tmp_path: Path):
    validator = PathValidator(tmp_path)
    adapter = SimpleNamespace(validator=validator)
    ports = PortAllocator()
    events = MagicMock(spec=EventForwarder)
    api = MagicMock(spec=httpx.AsyncClient)
    key_file = tmp_path / "agent_key"
    key_file.write_text(secrets.token_urlsafe(32))

    # 1. Neither configured: both None
    core_neither = SupervisorCore(
        docker_adapter=adapter,
        port_allocator=ports,
        event_forwarder=events,
        api_client=api,
        agent_key_file=key_file,
        gateway_container_id=None,
        coturn_container_id=None,
    )
    assert core_neither.gateway_container_id is None
    assert core_neither.coturn_container_id is None

    # 2. Coturn only: gateway is None, coturn is set
    core_coturn_only = SupervisorCore(
        docker_adapter=adapter,
        port_allocator=ports,
        event_forwarder=events,
        api_client=api,
        agent_key_file=key_file,
        gateway_container_id=None,
        coturn_container_id="coturn_c1",
    )
    assert core_coturn_only.gateway_container_id is None
    assert core_coturn_only.coturn_container_id == "coturn_c1"

    # 3. Paired: both set
    core_paired = SupervisorCore(
        docker_adapter=adapter,
        port_allocator=ports,
        event_forwarder=events,
        api_client=api,
        agent_key_file=key_file,
        gateway_container_id="gw_c1",
        coturn_container_id="coturn_c1",
    )
    assert core_paired.gateway_container_id == "gw_c1"
    assert core_paired.coturn_container_id == "coturn_c1"


@pytest.mark.asyncio
async def test_start_profile_fails_before_container_creation_when_coturn_missing(
    tmp_path: Path,
):
    validator = PathValidator(tmp_path)
    dirs = {
        key: tmp_path / key
        for key in ("runtime", "profile", "events", "exchange", "x11", "pulse")
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    adapter = SimpleNamespace(
        validator=validator,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        attach_profile_infrastructure=MagicMock(),
        start_browser_container=AsyncMock(),
        start_stream_container=AsyncMock(),
        teardown_profile=AsyncMock(),
    )
    ports = PortAllocator(30000, 30010)
    events = MagicMock(spec=EventForwarder)
    events.emit_event = AsyncMock(return_value=True)

    key_file = tmp_path / "agent_key"
    key_file.write_text(secrets.token_urlsafe(32))

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/runtime"):
            return httpx.Response(
                200,
                json={
                    "desired_state": "running",
                    "restart_blocked": False,
                    "runtime_instance_id": None,
                    "config_version": 1,
                },
            )
        if request.url.path.endswith("/bind"):
            return httpx.Response(200, json={"status": "bound"})
        if request.url.path.endswith("/observed"):
            return httpx.Response(200, json={"status": "observed"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test-api"
    ) as api:
        core = SupervisorCore(
            docker_adapter=adapter,
            port_allocator=ports,
            event_forwarder=events,
            api_client=api,
            agent_key_file=key_file,
            gateway_container_id=None,
            coturn_container_id=None,  # Missing coturn
        )

        with pytest.raises(
            (DockerSandboxError, RuntimeError),
            match="coturn infrastructure container is required",
        ):
            await core.start_profile("prof_missing_coturn", ProfileConfig(name="test"))

        # Container creation must NOT have been called
        adapter.start_browser_container.assert_not_called()
        adapter.start_stream_container.assert_not_called()
        adapter.attach_profile_infrastructure.assert_not_called()

        # Teardown called for cleanup
        adapter.teardown_profile.assert_awaited_once_with("prof_missing_coturn")

        # Failure reporting path must emit startup_failure exit event
        events.emit_event.assert_awaited()
        emit_call = events.emit_event.await_args
        assert emit_call.kwargs.get("exit_reason") == "startup_failure"
        assert emit_call.kwargs.get("exit_code") == 1
        assert emit_call.kwargs.get("event_type") == "exit"


def test_attach_profile_infrastructure_coturn_only(tmp_path: Path):
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
    )

    mock_net = MagicMock()
    mock_net.name = "t006-unit-net-prof1"
    mock_net.attrs = {
        "Labels": {
            "com.cbrowser.prefix": "t006-unit",
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.profile-id": "prof1",
        },
        "Containers": {},
    }
    mock_net.reload = MagicMock()
    mock_net.connect = MagicMock()
    client.networks.get.return_value = mock_net

    mock_coturn = MagicMock()
    mock_coturn.id = "coturn_id_123"
    mock_coturn.status = "running"
    mock_coturn.labels = {
        "com.cbrowser.prefix": "t006-unit",
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "coturn",
    }
    mock_coturn.attrs = {
        "NetworkSettings": {
            "Networks": {"t006-unit-net-prof1": {"IPAddress": "10.42.0.8"}}
        }
    }
    client.containers.get.side_effect = lambda cid: (
        mock_coturn if cid == "coturn_id_123" else MagicMock()
    )

    result = adapter.attach_profile_infrastructure(
        profile_id="prof1",
        gateway_container_id=None,
        coturn_container_id="coturn_id_123",
    )

    assert result["coturn_ip"] == "10.42.0.8"
    assert result["coturn_ice_address"] == "10.42.0.8:3478"
    assert result["ice_server"] == "turn:10.42.0.8:3478"
    assert "gateway_url" not in result
    assert "gateway_ip" not in result
    mock_net.connect.assert_called_once_with(mock_coturn)


@pytest.mark.asyncio
async def test_start_profile_stream_gateway_url_selection(tmp_path: Path):
    validator = PathValidator(tmp_path)
    dirs = {
        key: tmp_path / key
        for key in ("runtime", "profile", "events", "exchange", "x11", "pulse")
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    # Fake runner_info.json and required files for readiness
    info_path = dirs["runtime"] / "runner_info.json"
    (dirs["runtime"] / "x11").mkdir(exist_ok=True)
    (dirs["runtime"] / "x11" / "X99").touch()
    (dirs["runtime"] / "pulse").mkdir(exist_ok=True)
    (dirs["runtime"] / "pulse" / "pulse.sock").touch()
    (dirs["runtime"] / "Xauthority").touch()
    (dirs["runtime"] / "agent.sock").touch()

    key_file = tmp_path / "agent_key"
    key_file.write_text(secrets.token_urlsafe(32))

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

    # 1. Case A: Coturn only -> Stream should use SupervisorCore.gateway_url
    ports = PortAllocator(30000, 30010)
    events = MagicMock(spec=EventForwarder)
    events.emit_event = AsyncMock(return_value=True)

    adapter_coturn_only = SimpleNamespace(
        validator=validator,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        attach_profile_infrastructure=MagicMock(
            return_value={
                "coturn_ip": "10.42.0.8",
                "coturn_ice_address": "10.42.0.8:3478",
                "ice_server": "turn:10.42.0.8:3478",
            }
        ),
        start_browser_container=AsyncMock(return_value=mock_browser_container),
        start_stream_container=AsyncMock(return_value=mock_stream_container),
        teardown_profile=AsyncMock(),
    )

    # To satisfy browser_runtime_ready during start_profile:
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

    adapter_coturn_only.start_browser_container.side_effect = write_runner_info

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test-api"
    ) as api:
        core = SupervisorCore(
            docker_adapter=adapter_coturn_only,
            port_allocator=ports,
            event_forwarder=events,
            api_client=api,
            gateway_url="ws://supervisor-host-gw:18097",
            token_file=None,
            agent_key_file=key_file,
            gateway_control=mock_gateway_control,
            gateway_container_id=None,
            coturn_container_id="turn_only_id",
        )

        session = await core.start_profile("prof_test", ProfileConfig(name="test"))
        assert session.observed_state == "running"

        # Verify attach_profile_infrastructure called with gateway=None
        adapter_coturn_only.attach_profile_infrastructure.assert_called_once_with(
            "prof_test", None, "turn_only_id"
        )
        # Verify start_stream_container got SupervisorCore.gateway_url
        call_kwargs = adapter_coturn_only.start_stream_container.call_args.kwargs
        assert call_kwargs["gateway_url"] == "ws://supervisor-host-gw:18097"
        assert call_kwargs["media_addresses"]["coturn_ip"] == "10.42.0.8"

    # 2. Case B: Paired -> Stream should use media_addresses["gateway_url"]
    ports2 = PortAllocator(30000, 30010)
    adapter_paired = SimpleNamespace(
        validator=validator,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        attach_profile_infrastructure=MagicMock(
            return_value={
                "gateway_ip": "10.42.0.3",
                "gateway_url": "ws://10.42.0.3:18097",
                "coturn_ip": "10.42.0.8",
                "coturn_ice_address": "10.42.0.8:3478",
                "ice_server": "turn:10.42.0.8:3478",
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
            port_allocator=ports2,
            event_forwarder=events,
            api_client=api,
            gateway_url="ws://supervisor-host-gw:18097",
            token_file=None,
            agent_key_file=key_file,
            gateway_control=mock_gateway_control,
            gateway_container_id="gw_paired_id",
            coturn_container_id="turn_paired_id",
        )

        session2 = await core_paired.start_profile(
            "prof_test2", ProfileConfig(name="test2")
        )
        assert session2.observed_state == "running"

    adapter_paired.attach_profile_infrastructure.assert_called_once_with(
        "prof_test2", "gw_paired_id", "turn_paired_id"
    )
    call_kwargs2 = adapter_paired.start_stream_container.call_args.kwargs
    assert call_kwargs2["gateway_url"] == "ws://10.42.0.3:18097"
