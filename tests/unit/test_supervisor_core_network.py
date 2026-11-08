"""Unit tests for SupervisorCore edge rebuild and stream network drift convergence."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from cbrowser.supervisor.core import ActiveSession, SupervisorCore


@pytest.fixture
def mock_docker_adapter(tmp_path):
    adapter = MagicMock()
    adapter.prefix = "cbrowser"
    adapter.validator = MagicMock()
    adapter.validator.data_root = tmp_path

    secret_dir = tmp_path / "secret" / "prof1"
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("dummy-secret")
    runtime_dir = tmp_path / "runtime" / "prof1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    adapter.validator.get_secret_dir = MagicMock(return_value=secret_dir)
    adapter.validator.get_runtime_dir = MagicMock(return_value=runtime_dir)

    adapter.rebuild_caddy_container = AsyncMock(return_value={"rebuilt": True})
    adapter.get_stream_container_name = MagicMock(return_value="cbrowser-stream-prof1")
    adapter.cleanup_container_by_name = MagicMock()
    adapter.attach_profile_infrastructure = MagicMock(return_value={"gateway_url": "ws://gateway", "gateway_ip": "172.18.0.2"})
    adapter.get_profile_containers = MagicMock()

    # Mock browser and stream container
    b_container = MagicMock()
    b_container.name = "cbrowser-browser-prof1"

    s_container = MagicMock()
    s_container.id = "s-cid-1"
    s_container.labels = {
        "com.cbrowser.stream.bind-host": "127.0.0.1",
        "com.cbrowser.stream.advertised-ip": "127.0.0.1",
    }
    adapter.get_profile_containers.return_value = {
        "browser": b_container,
        "stream": s_container,
    }
    adapter.start_stream_container = AsyncMock(return_value=s_container)
    return adapter


@pytest.mark.asyncio
async def test_rebuild_edge_proxy(mock_docker_adapter, tmp_path):
    core = SupervisorCore(
        docker_adapter=mock_docker_adapter,
        port_allocator=MagicMock(),
        event_forwarder=MagicMock(),
        api_client=MagicMock(),
    )
    res = await core.rebuild_edge_proxy(
        target_version=2,
        bind_host="0.0.0.0",
        https_port=56661,
        caddyfile_path=str(tmp_path / "Caddyfile"),
    )
    assert res["status"] == "ok"
    mock_docker_adapter.rebuild_caddy_container.assert_awaited_once_with(
        bind_host="0.0.0.0",
        https_port=56661,
        caddyfile_path=str(tmp_path / "Caddyfile"),
    )


@pytest.mark.asyncio
async def test_converge_network_streams_detects_drift(mock_docker_adapter, tmp_path):
    core = SupervisorCore(
        docker_adapter=mock_docker_adapter,
        port_allocator=MagicMock(),
        event_forwarder=MagicMock(),
        api_client=MagicMock(),
    )
    # Register an active session running on 127.0.0.1
    session = ActiveSession(
        profile_id="prof1",
        runtime_instance_id="inst-1",
        config_version=1,
        udp_mux_port=30001,
        browser_container_id="b-cid-1",
        stream_container_id="s-cid-1",
    )
    core._sessions["prof1"] = session

    # Target is LAN mode: bind_host=0.0.0.0, advertised_ip=192.168.31.76
    res = await core.converge_network_streams(
        target_version=2,
        bind_host="0.0.0.0",
        advertised_ip="192.168.31.76",
    )
    assert res["status"] == "ok"
    assert res["rebuilt_streams"] == 1
    mock_docker_adapter.start_stream_container.assert_awaited_once()
