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
    from pathlib import Path

    network_dir = tmp_path / "network"
    network_dir.mkdir(parents=True, exist_ok=True)
    (network_dir / "Caddyfile.staging.op-1").write_text("caddy-candidate")
    mock_docker_adapter.validator.validate_safe_path = MagicMock(
        side_effect=lambda p, allow_create=True: Path(p)
    )
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
        caddyfile_path="Caddyfile.staging.op-1",
    )
    assert res["status"] == "ok"
    assert res["rebuilt"] is True
    # P1-2: the rebuild binds the persistent file, never the staging file.
    mock_docker_adapter.rebuild_caddy_container.assert_awaited_once_with(
        bind_host="0.0.0.0",
        https_port=56661,
        caddyfile_path=str(network_dir / "Caddyfile"),
    )
    assert (network_dir / "Caddyfile").read_text() == "caddy-candidate"


@pytest.mark.asyncio
async def test_rebuild_edge_proxy_rejects_absolute_path(
    mock_docker_adapter, tmp_path
):
    core = SupervisorCore(
        docker_adapter=mock_docker_adapter,
        port_allocator=MagicMock(),
        event_forwarder=MagicMock(),
        api_client=MagicMock(),
    )
    with pytest.raises(Exception, match="basename"):
        await core.rebuild_edge_proxy(
            target_version=2,
            bind_host="0.0.0.0",
            https_port=56661,
            caddyfile_path=str(tmp_path / "Caddyfile"),
        )
    mock_docker_adapter.rebuild_caddy_container.assert_not_awaited()


@pytest.mark.asyncio
async def test_edge_receipt_claims_verified_only_after_docker(
    mock_docker_adapter, tmp_path
):
    """docker_verified must not be ok before the Docker operation: a staged
    receipt stays unverified when Docker fails and flips only on success."""
    from pathlib import Path

    from cbrowser.supervisor.docker_adapter import DockerSandboxError

    network_dir = tmp_path / "network"
    network_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "control" / "operations").mkdir(parents=True, exist_ok=True)
    mock_docker_adapter.validator.validate_safe_path = MagicMock(
        side_effect=lambda p, allow_create=True: Path(p)
    )
    core = SupervisorCore(
        docker_adapter=mock_docker_adapter,
        port_allocator=MagicMock(),
        event_forwarder=MagicMock(),
        api_client=MagicMock(),
    )

    (network_dir / "Caddyfile.staging.op-ok").write_text("caddy-ok")
    res = await core.rebuild_edge_proxy(
        target_version=2,
        bind_host="127.0.0.1",
        https_port=56661,
        caddyfile_path="Caddyfile.staging.op-ok",
        operation_id="op-ok",
        execution_generation=1,
    )
    assert res["status"] == "ok"
    ok_request = {
        "operation_id": "op-ok",
        "execution_generation": 1,
        "phase": "installing",
        "resource": "caddy",
    }
    ok_receipt = core.operations.network_receipt(
        "op-ok", "installing", "caddy", ok_request
    )
    assert ok_receipt["status"] == "ok"
    assert ok_receipt["docker_verified"] is True

    mock_docker_adapter.rebuild_caddy_container = AsyncMock(
        side_effect=DockerSandboxError("docker down")
    )
    (network_dir / "Caddyfile.staging.op-bad").write_text("caddy-bad")
    with pytest.raises(DockerSandboxError, match="docker down"):
        await core.rebuild_edge_proxy(
            target_version=3,
            bind_host="127.0.0.1",
            https_port=56661,
            caddyfile_path="Caddyfile.staging.op-bad",
            operation_id="op-bad",
            execution_generation=2,
        )
    bad_request = {
        "operation_id": "op-bad",
        "execution_generation": 2,
        "phase": "installing",
        "resource": "caddy",
    }
    bad_receipt = core.operations.network_receipt(
        "op-bad", "installing", "caddy", bad_request
    )
    assert bad_receipt["status"] == "staged"
    assert bad_receipt["docker_verified"] is False


@pytest.mark.asyncio
async def test_converge_network_streams_blocks_commit_on_replace_failure(
    mock_docker_adapter, tmp_path
):
    from cbrowser.supervisor.docker_adapter import DockerSandboxError

    core = SupervisorCore(
        docker_adapter=mock_docker_adapter,
        port_allocator=MagicMock(),
        event_forwarder=MagicMock(),
        api_client=MagicMock(),
    )
    session = ActiveSession(
        profile_id="prof1",
        runtime_instance_id="inst-1",
        config_version=1,
        udp_mux_port=30001,
        browser_container_id="b-cid-1",
        stream_container_id="s-cid-1",
    )
    core._sessions["prof1"] = session
    core._replace_stream_only = AsyncMock(return_value=False)

    with pytest.raises(DockerSandboxError, match="network commit blocked"):
        await core.converge_network_streams(
            target_version=2,
            bind_host="0.0.0.0",
            advertised_ip="192.168.31.76",
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
