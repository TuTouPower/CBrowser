"""Unit tests verifying baseline fixture regressions and ownership cleanup contracts."""

from __future__ import annotations

import asyncio
import secrets
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import docker.errors
import httpx
import pytest
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT
from cbrowser.domain.models import NetworkAccessConfig
from cbrowser.network_config import generate_caddyfile
from cbrowser.runtime_agent.socket_root import (
    AGENT_SOCKET_ROOT_ENV,
    DEFAULT_AGENT_SOCKET_ROOT,
)


from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from cbrowser.stream_agent.messaging import (  # noqa: E402
    build_register_envelope,
    build_register_payload,
    iso_now,
)
from cbrowser.supervisor.agent_credentials import AgentCredentials  # noqa: E402
from gateway_probe.topology import GatewayTopologyHarness  # noqa: E402
from supervisor_recovery_probe.gateway_service import (  # noqa: E402
    FakeGatewayApiClient,
    ProductionGatewayService,
)
from supervisor_recovery_probe.offline_fixture import (  # noqa: E402
    RealApiProcess,
    RealSupervisorContainer,
    get_free_port,
)


def _set_test_images_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    h = secrets.token_hex(32)
    monkeypatch.setenv("CBROWSER_RUNTIME_TEST_IMAGE", f"sha256:{h}")
    monkeypatch.setenv("CBROWSER_STREAM_TEST_IMAGE", f"sha256:{h}")
    monkeypatch.setenv("CBROWSER_GATEWAY_IMAGE", f"sha256:{h}")
    monkeypatch.setenv("CBROWSER_SUPERVISOR_TEST_IMAGE", f"sha256:{h}")
    monkeypatch.setenv("CBROWSER_API_TEST_IMAGE", f"sha256:{h}")
    monkeypatch.setenv("CBROWSER_CADDY_TEST_IMAGE", f"sha256:{h}")
    monkeypatch.setenv("CBROWSER_RUNTIME_ENGINE_CACHE", str(tmp_path / "engine"))
    monkeypatch.setenv("CBROWSER_RUNTIME_GEOIP_CACHE", str(tmp_path / "geoip"))
    (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
    (tmp_path / "geoip").mkdir(parents=True, exist_ok=True)


def test_real_supervisor_container_gateway_port_resolution_and_cli_arg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RealSupervisorContainer must pass --gateway-port matching gateway_url."""
    _set_test_images_env(monkeypatch, tmp_path)
    token_file = tmp_path / "sup_token"
    token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    token_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    gw_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    dynamic_port = 28099
    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "sup_cid_12345"
    mock_container.status = "running"
    mock_docker.containers.run.return_value = mock_container

    container = RealSupervisorContainer(
        api_url="http://host.docker.internal:8000",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "engine",
        geoip_cache=tmp_path / "geoip",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_url=f"ws://host.docker.internal:{dynamic_port}",
        gateway_control_url=f"http://host.docker.internal:{dynamic_port}",
        gateway_token_file=gw_token_file,
        prefix="test-dyn",
        port=8005,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=mock_docker,
    )

    with patch("httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http.get.return_value = mock_resp
        mock_http.__enter__.return_value = mock_http
        mock_client_cls.return_value = mock_http

        container.start(timeout_sec=0.5)

    assert mock_docker.containers.run.called
    _, run_kwargs = mock_docker.containers.run.call_args
    cmd = run_kwargs["command"]
    assert "--gateway-port" in cmd, "cmd must contain --gateway-port"
    idx = cmd.index("--gateway-port")
    assert cmd[idx + 1] == str(dynamic_port)
    assert run_kwargs["ports"] == {"8005/tcp": ("127.0.0.1", 8005)}


def test_real_supervisor_container_defaults_to_authoritative_gateway_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RealSupervisorContainer must default to DEFAULT_GATEWAY_PORT."""
    _set_test_images_env(monkeypatch, tmp_path)
    token_file = tmp_path / "sup_token"
    token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    token_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    gw_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "sup_cid_default"
    mock_container.status = "running"
    mock_docker.containers.run.return_value = mock_container

    container = RealSupervisorContainer(
        api_url="http://host.docker.internal:8000",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "engine",
        geoip_cache=tmp_path / "geoip",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_url="ws://host.docker.internal",
        gateway_control_url=f"http://host.docker.internal:{DEFAULT_GATEWAY_PORT}",
        gateway_token_file=gw_token_file,
        prefix="test-def",
        port=8005,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=mock_docker,
    )

    with patch("httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http.get.return_value = mock_resp
        mock_http.__enter__.return_value = mock_http
        mock_client_cls.return_value = mock_http

        container.start(timeout_sec=0.5)

    _, run_kwargs = mock_docker.containers.run.call_args
    cmd = run_kwargs["command"]
    assert "--gateway-port" in cmd
    idx = cmd.index("--gateway-port")
    assert cmd[idx + 1] == str(DEFAULT_GATEWAY_PORT)


def test_real_supervisor_container_sigkill_asserts_exit_code_137(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sigkill() must execute Docker kill, verify ExitCode 137, and remove container."""
    _set_test_images_env(monkeypatch, tmp_path)
    token_file = tmp_path / "sup_token"
    token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    token_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    gw_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    mock_docker = MagicMock()
    mock_c = MagicMock()
    mock_c.id = "cid_sigkill_test"
    mock_c.attrs = {"State": {"Status": "exited", "ExitCode": 137, "OOMKilled": False}}
    mock_c.logs.return_value = b"container log content"

    container = RealSupervisorContainer(
        api_url="http://host.docker.internal:8000",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "engine",
        geoip_cache=tmp_path / "geoip",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_url="ws://host.docker.internal",
        gateway_control_url=f"http://host.docker.internal:{DEFAULT_GATEWAY_PORT}",
        gateway_token_file=gw_token_file,
        prefix="test-sigkill",
        port=8005,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=mock_docker,
    )
    container.container = mock_c

    container.sigkill(timeout_sec=0.5)

    mock_c.kill.assert_called_once_with(signal="SIGKILL")
    mock_c.reload.assert_called()
    mock_c.remove.assert_called_once_with(force=True, v=True)
    assert container.container is None
    assert container.last_container_id == "cid_sigkill_test"
    assert (tmp_path / "sup.log").read_bytes() == b"container log content"


def test_real_supervisor_container_sigkill_remove_error_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sigkill() must raise RuntimeError on removal error and keep reference."""
    _set_test_images_env(monkeypatch, tmp_path)
    token_file = tmp_path / "sup_token"
    token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    token_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    gw_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    mock_docker = MagicMock()
    mock_c = MagicMock()
    mock_c.id = "cid_sigkill_remove_fail"
    mock_c.attrs = {"State": {"Status": "exited", "ExitCode": 137, "OOMKilled": False}}
    mock_c.logs.return_value = b"container log content"
    mock_c.remove.side_effect = docker.errors.APIError("Daemon remove error on sigkill")

    container = RealSupervisorContainer(
        api_url="http://host.docker.internal:8000",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "engine",
        geoip_cache=tmp_path / "geoip",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_url="ws://host.docker.internal",
        gateway_control_url=f"http://host.docker.internal:{DEFAULT_GATEWAY_PORT}",
        gateway_token_file=gw_token_file,
        prefix="test-sigkill-fail",
        port=8005,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=mock_docker,
    )
    container.container = mock_c

    with pytest.raises(
        RuntimeError, match="Supervisor container remove failed on sigkill"
    ):
        container.sigkill(timeout_sec=0.5)

    mock_c.kill.assert_called_once_with(signal="SIGKILL")
    mock_c.reload.assert_called()
    assert container.container is mock_c
    assert container.last_container_id == "cid_sigkill_remove_fail"


def test_real_supervisor_container_mounts_isolate_control_db_bait_and_sync_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mounts must isolate control.db bait in parent directory and sync 0600 secrets."""
    _set_test_images_env(monkeypatch, tmp_path)

    # Place control.db bait in the parent tmp_path directory where tokens reside
    bait_db = tmp_path / "control.db"
    bait_db.write_text("API SQLite control database bait", encoding="utf-8")

    token_file = tmp_path / "sup_token"
    token_file.write_text("token_secret_val", encoding="utf-8")
    token_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text("gw_secret_val", encoding="utf-8")
    gw_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text("agent_secret_val", encoding="utf-8")
    agent_key_file.chmod(0o600)

    mock_docker = MagicMock()
    mock_c = MagicMock()
    mock_c.id = "sup_cid_bait_test"
    mock_c.status = "running"
    mock_docker.containers.run.return_value = mock_c

    data_root = tmp_path / "isolated_data"
    container = RealSupervisorContainer(
        api_url="http://host.docker.internal:8000",
        data_root=data_root,
        engine_cache=tmp_path / "engine",
        geoip_cache=tmp_path / "geoip",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_url="ws://host.docker.internal",
        gateway_control_url=f"http://host.docker.internal:{DEFAULT_GATEWAY_PORT}",
        gateway_token_file=gw_token_file,
        prefix="test-bait",
        port=8005,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=mock_docker,
    )

    with patch("httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http.get.return_value = mock_resp
        mock_http.__enter__.return_value = mock_http
        mock_client_cls.return_value = mock_http

        container.start(timeout_sec=0.5)

    _, run_kwargs = mock_docker.containers.run.call_args
    volumes = run_kwargs["volumes"]

    # 1. Parent tmp_path containing control.db MUST NOT be mounted
    assert str(tmp_path) not in volumes
    assert str(bait_db) not in volumes
    for src_bind in volumes:
        assert "control.db" not in src_bind

    # 2. Strict allowed subdirectories only
    expected_subs = {
        str(data_root / "profiles"),
        str(data_root / "runtime"),
        str(data_root / "runtime-events"),
        str(data_root / "artifacts"),
        str(data_root / "spool"),
        str(data_root / "control"),
        str(tmp_path / "engine"),
        str(tmp_path / "geoip"),
        "/var/run/docker.sock",
        DEFAULT_AGENT_SOCKET_ROOT,
    }
    assert set(volumes.keys()) == expected_subs
    # Supervisor initialization writer contract: caches are mounted rw
    assert volumes[str(tmp_path / "engine")]["mode"] == "rw"
    assert volumes[str(tmp_path / "geoip")]["mode"] == "rw"
    assert volumes["/var/run/docker.sock"]["mode"] == "ro"
    assert volumes[DEFAULT_AGENT_SOCKET_ROOT]["mode"] == "rw"
    assert (
        run_kwargs["environment"][AGENT_SOCKET_ROOT_ENV]
        == DEFAULT_AGENT_SOCKET_ROOT
    )

    # 3. Secret file synced to data_root/control with 0600 mode
    synced_token = data_root / "control" / "sup_token"
    assert synced_token.is_file()
    assert synced_token.read_text(encoding="utf-8") == "token_secret_val"
    assert stat.S_IMODE(synced_token.stat().st_mode) == 0o600


def test_real_supervisor_container_security_options_match_container_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RealSupervisorContainer must configure cap_drop, cap_add, and security_opt."""
    _set_test_images_env(monkeypatch, tmp_path)
    token_file = tmp_path / "sup_token"
    token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    token_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    gw_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    mock_docker = MagicMock()
    mock_c = MagicMock()
    mock_c.id = "sup_cid_sec"
    mock_c.status = "running"
    mock_docker.containers.run.return_value = mock_c

    container = RealSupervisorContainer(
        api_url="http://host.docker.internal:8000",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "engine",
        geoip_cache=tmp_path / "geoip",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_url="ws://host.docker.internal",
        gateway_control_url=f"http://host.docker.internal:{DEFAULT_GATEWAY_PORT}",
        gateway_token_file=gw_token_file,
        prefix="test-sec",
        port=8005,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=mock_docker,
    )

    with patch("httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http.get.return_value = mock_resp
        mock_http.__enter__.return_value = mock_http
        mock_client_cls.return_value = mock_http

        container.start(timeout_sec=0.5)

    _, run_kwargs = mock_docker.containers.run.call_args
    assert run_kwargs["read_only"] is True
    assert run_kwargs["cap_drop"] == ["ALL"]
    assert run_kwargs["cap_add"] == ["FOWNER", "DAC_OVERRIDE", "CHOWN"]
    assert run_kwargs["security_opt"] == ["no-new-privileges:true"]
    assert run_kwargs["tmpfs"] == {"/tmp": "rw,size=256m"}


def test_real_supervisor_container_stop_failure_propagates_and_retains_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop() must raise RuntimeError on removal error and keep container reference."""
    _set_test_images_env(monkeypatch, tmp_path)
    token_file = tmp_path / "sup_token"
    token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    token_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    gw_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    mock_docker = MagicMock()
    mock_c = MagicMock()
    mock_c.id = "cid_remove_fail"
    mock_c.remove.side_effect = docker.errors.APIError("Daemon remove error")

    container = RealSupervisorContainer(
        api_url="http://host.docker.internal:8000",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "engine",
        geoip_cache=tmp_path / "geoip",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_url="ws://host.docker.internal",
        gateway_control_url=f"http://host.docker.internal:{DEFAULT_GATEWAY_PORT}",
        gateway_token_file=gw_token_file,
        prefix="test-stop-fail",
        port=8005,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=mock_docker,
    )
    container.container = mock_c

    with pytest.raises(RuntimeError, match="Supervisor container stop/remove failed"):
        container.stop()

    assert container.container is not None


def test_real_supervisor_container_start_failure_with_stop_failure_chains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """start() failure coupled with stop() failure must chain both exceptions."""
    _set_test_images_env(monkeypatch, tmp_path)
    token_file = tmp_path / "sup_token"
    token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    token_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    gw_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    mock_docker = MagicMock()
    mock_c = MagicMock()
    mock_c.id = "cid_start_fail"
    mock_c.status = "dead"
    mock_c.remove.side_effect = docker.errors.APIError("Stop cleanup failed")
    mock_docker.containers.run.return_value = mock_c

    container = RealSupervisorContainer(
        api_url="http://host.docker.internal:8000",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "engine",
        geoip_cache=tmp_path / "geoip",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_url="ws://host.docker.internal",
        gateway_control_url=f"http://host.docker.internal:{DEFAULT_GATEWAY_PORT}",
        gateway_token_file=gw_token_file,
        prefix="test-chain",
        port=8005,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=mock_docker,
    )

    with (
        patch("httpx.Client"),
        pytest.raises(
            RuntimeError, match="Supervisor container stop/remove failed"
        ) as exc_info,
    ):
        container.start(timeout_sec=0.2)

    assert exc_info.value.__cause__ is not None
    assert "Supervisor container exited (dead)" in str(exc_info.value.__cause__)


@pytest.mark.asyncio
async def test_gateway_topology_harness_secrets_permission_0600(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GatewayTopologyHarness.start must write every secret file as 0600."""
    _set_test_images_env(monkeypatch, tmp_path)

    mock_docker = MagicMock()
    mock_docker.networks.create.return_value.name = "test-edge"
    mock_docker.api.inspect_network.return_value = {
        "IPAM": {"Config": [{"Subnet": "192.168.100.0/24"}]}
    }

    def fake_run(role, image_id, **kwargs):
        container = MagicMock()
        container.id = f"cid_{role}"
        container.name = f"test-{role}"
        container.status = "running"
        container.attrs = {
            "NetworkSettings": {
                "Networks": {"test-edge": {"IPAddress": "192.168.100.5"}},
                "Ports": {
                    "443/tcp": [{"HostPort": "38443"}],
                    "8000/tcp": [{"HostPort": "38000"}],
                    "8005/tcp": [{"HostPort": "38005"}],
                    f"{DEFAULT_GATEWAY_PORT}/tcp": [{"HostPort": "38080"}],
                },
            }
        }
        return container

    with (
        patch("docker.from_env", return_value=mock_docker),
        patch("gateway_probe.topology.prepare_selkies_web_assets"),
        patch("gateway_probe.topology.wait_until_ready"),
    ):
        harness = GatewayTopologyHarness(work_dir=tmp_path / "work")
        monkeypatch.setattr(harness, "_run_container", fake_run)
        await harness.start()

    for name, fpath in harness.key_files.items():
        mode = stat.S_IMODE(fpath.stat().st_mode)
        assert mode == 0o600, (
            f"Secret file {name} ({fpath}) must have mode 0600, got {oct(mode)}"
        )
    control_mode = stat.S_IMODE(harness.control_dir.stat().st_mode)
    assert control_mode == 0o700, (
        f"Secret directory must have mode 0700, got {oct(control_mode)}"
    )


@pytest.mark.asyncio
async def test_gateway_topology_harness_cleanup_ownership_label_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real cleanup must reject deleting networks with foreign labels."""
    _set_test_images_env(monkeypatch, tmp_path)

    mock_docker = MagicMock()
    with patch("docker.from_env", return_value=mock_docker):
        harness = GatewayTopologyHarness(work_dir=tmp_path / "work")

        owned_c = MagicMock()
        owned_c.name = f"{harness.prefix}-c1"
        owned_c.labels = {"com.cbrowser.prefix": harness.prefix}

        foreign_c = MagicMock()
        foreign_c.name = f"{harness.prefix}-c_foreign"
        foreign_c.labels = {"com.cbrowser.prefix": "different-prefix"}

        mock_docker.containers.list.return_value = [owned_c, foreign_c]

        owned_net = MagicMock()
        owned_net.name = f"{harness.prefix}-edge"
        owned_net.attrs = {
            "Labels": {"com.cbrowser.prefix": harness.prefix},
            "Containers": {},
        }

        foreign_net = MagicMock()
        foreign_net.name = f"{harness.prefix}-foreign-net"
        foreign_net.attrs = {
            "Labels": {"com.cbrowser.prefix": "other-prefix"},
            "Containers": {},
        }

        mock_docker.networks.list.return_value = [owned_net, foreign_net]

        await harness.cleanup()

        owned_c.remove.assert_called_once_with(force=True, v=True)
        foreign_c.remove.assert_not_called()

        owned_net.remove.assert_called_once()
        foreign_net.remove.assert_not_called()


@pytest.mark.asyncio
async def test_gateway_topology_harness_cleanup_refuses_when_network_not_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real cleanup must raise RuntimeError when owned network is not empty."""
    _set_test_images_env(monkeypatch, tmp_path)

    mock_docker = MagicMock()
    with patch("docker.from_env", return_value=mock_docker):
        harness = GatewayTopologyHarness(work_dir=tmp_path / "work")

        mock_docker.containers.list.return_value = []

        busy_net = MagicMock()
        busy_net.name = f"{harness.prefix}-busy"
        busy_net.attrs = {
            "Labels": {"com.cbrowser.prefix": harness.prefix},
            "Containers": {"c_other_id": {"Name": "unmanaged_container"}},
        }
        mock_docker.networks.list.return_value = [busy_net]

        with pytest.raises(RuntimeError, match="network_not_empty"):
            await harness.cleanup()

        busy_net.remove.assert_not_called()


@pytest.mark.asyncio
async def test_gateway_topology_harness_cleanup_fails_on_container_remove_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real cleanup must raise RuntimeError when removal fails with APIError."""
    _set_test_images_env(monkeypatch, tmp_path)

    mock_docker = MagicMock()
    with patch("docker.from_env", return_value=mock_docker):
        harness = GatewayTopologyHarness(work_dir=tmp_path / "work")

        failing_c = MagicMock()
        failing_c.name = f"{harness.prefix}-fail"
        failing_c.labels = {"com.cbrowser.prefix": harness.prefix}
        failing_c.remove.side_effect = docker.errors.APIError("Docker daemon error")

        mock_docker.containers.list.return_value = [failing_c]
        mock_docker.networks.list.return_value = []

        with pytest.raises(RuntimeError, match="container_remove"):
            await harness.cleanup()


@pytest.mark.asyncio
async def test_gateway_topology_harness_start_failure_triggers_real_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real cleanup is triggered by start failure; re-raises original error."""
    _set_test_images_env(monkeypatch, tmp_path)

    mock_docker = MagicMock()
    with (
        patch("docker.from_env", return_value=mock_docker),
        patch("gateway_probe.topology.prepare_selkies_web_assets"),
    ):
        harness = GatewayTopologyHarness(work_dir=tmp_path / "work")

        owned_c = MagicMock()
        owned_c.name = f"{harness.prefix}-c1"
        owned_c.labels = {"com.cbrowser.prefix": harness.prefix}
        mock_docker.containers.list.return_value = [owned_c]
        mock_docker.networks.list.return_value = []

        with (
            patch.object(
                harness,
                "_run_container",
                side_effect=RuntimeError("Simulated container startup error"),
            ),
            pytest.raises(RuntimeError, match="Simulated container startup error"),
        ):
            await harness.start()

        owned_c.remove.assert_called_once_with(force=True, v=True)


@pytest.mark.asyncio
async def test_gateway_topology_harness_start_failure_with_cleanup_failure_chains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If cleanup also fails, both exceptions are preserved via cause chaining."""
    _set_test_images_env(monkeypatch, tmp_path)

    mock_docker = MagicMock()
    with (
        patch("docker.from_env", return_value=mock_docker),
        patch("gateway_probe.topology.prepare_selkies_web_assets"),
    ):
        harness = GatewayTopologyHarness(work_dir=tmp_path / "work")

        failing_c = MagicMock()
        failing_c.name = f"{harness.prefix}-fail"
        failing_c.labels = {"com.cbrowser.prefix": harness.prefix}
        failing_c.remove.side_effect = docker.errors.APIError("Cleanup Docker error")
        mock_docker.containers.list.return_value = [failing_c]
        mock_docker.networks.list.return_value = []

        with (
            patch.object(
                harness,
                "_run_container",
                side_effect=RuntimeError("Start container failure"),
            ),
            pytest.raises(
                RuntimeError, match="Cleanup encountered failures"
            ) as exc_info,
        ):
            await harness.start()

        assert exc_info.value.__cause__ is not None
        assert "Start container failure" in str(exc_info.value.__cause__)


def test_caddyfile_generator_uses_authoritative_gateway_port() -> None:
    """generate_caddyfile must proxy /stream/* to DEFAULT_GATEWAY_PORT."""
    cfg = NetworkAccessConfig(lan_access_enabled=False)
    content = generate_caddyfile(cfg)
    assert f":{DEFAULT_GATEWAY_PORT}" in content
    assert "18097" not in content

    custom = generate_caddyfile(
        cfg,
        gateway_upstream="http://gateway:18088",
    )
    assert ":18088" in custom


@pytest.mark.asyncio
async def test_gateway_topology_harness_environment_and_ports_consistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Topology harness must configure Gateway on DEFAULT_GATEWAY_PORT."""
    _set_test_images_env(monkeypatch, tmp_path)

    mock_docker = MagicMock()
    mock_net = MagicMock()
    mock_net.name = "test-edge"
    mock_docker.networks.create.return_value = mock_net
    mock_docker.api.inspect_network.return_value = {
        "IPAM": {"Config": [{"Subnet": "192.168.100.0/24"}]}
    }
    run_calls: dict[str, dict] = {}

    def fake_run(role, image_id, **kwargs):
        run_calls[role] = kwargs
        c = MagicMock()
        c.id = f"cid_{role}"
        c.name = f"test-{role}"
        c.status = "running"
        c.attrs = {
            "NetworkSettings": {
                "Networks": {"test-edge": {"IPAddress": "192.168.100.5"}},
                "Ports": {
                    "443/tcp": [{"HostPort": "38443"}],
                    "8000/tcp": [{"HostPort": "38000"}],
                    "8005/tcp": [{"HostPort": "38005"}],
                    f"{DEFAULT_GATEWAY_PORT}/tcp": [{"HostPort": "38080"}],
                },
            }
        }
        return c

    with (
        patch("docker.from_env", return_value=mock_docker),
        patch("gateway_probe.topology.prepare_selkies_web_assets"),
        patch("gateway_probe.topology.wait_until_ready"),
    ):
        harness = GatewayTopologyHarness(work_dir=tmp_path / "work")
        harness.prefix = "test-check"
        monkeypatch.setattr(harness, "_run_container", fake_run)

        await harness.start()

        gw_kwargs = run_calls["gateway"]
        assert gw_kwargs["environment"]["CBROWSER_GATEWAY_PORT"] == str(
            DEFAULT_GATEWAY_PORT
        )
        assert f"{DEFAULT_GATEWAY_PORT}/tcp" in gw_kwargs["ports"]
        assert "18097" not in str(gw_kwargs["ports"])

        sup_kwargs = run_calls["supervisor"]
        cmd = sup_kwargs["command"]
        assert "--gateway-port" in cmd
        p_idx = cmd.index("--gateway-port")
        assert cmd[p_idx + 1] == str(DEFAULT_GATEWAY_PORT)

        caddy_file = tmp_path / "work" / "Caddyfile"
        assert caddy_file.is_file()
        assert f":{DEFAULT_GATEWAY_PORT}" in caddy_file.read_text()
        assert "18097" not in caddy_file.read_text()


def test_cleanup_prefixed_resources_reload_error_skips_removal() -> None:
    """Network reload error must be collected and network removal skipped."""
    from gateway_probe.topology import cleanup_prefixed_resources

    mock_docker = MagicMock()
    mock_docker.containers.list.return_value = []

    failing_net = MagicMock()
    failing_net.name = "test-fail-reload"
    failing_net.attrs = {"Labels": {"com.cbrowser.prefix": "test-prefix"}}
    failing_net.reload.side_effect = docker.errors.APIError("Network reload failed")

    mock_docker.networks.list.return_value = [failing_net]

    with pytest.raises(RuntimeError, match="network_reload"):
        cleanup_prefixed_resources(mock_docker, "test-prefix")

    failing_net.remove.assert_not_called()


@pytest.mark.asyncio
async def test_supervisor_lifecycle_in_thread_keeps_async_event_loop_responsive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invoking container.start via to_thread must keep asyncio loop unblocked."""
    from aiohttp import web

    _set_test_images_env(monkeypatch, tmp_path)
    token_file = tmp_path / "sup_token"
    token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    token_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text(secrets.token_hex(32), encoding="utf-8")
    gw_token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    # 1. Start a local responsive aiohttp web app on the current event loop
    app = web.Application()
    ping_hit = False

    async def handle_ping(request):
        nonlocal ping_hit
        ping_hit = True
        return web.Response(text="pong")

    app.router.add_get("/ping", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        test_port = s.getsockname()[1]
    site = web.TCPSite(runner, "127.0.0.1", test_port)
    await site.start()

    # 2. Mock container start with simulated polling delay inside worker thread
    mock_docker = MagicMock()
    mock_c = MagicMock()
    mock_c.id = "cid_thread_test"
    mock_c.status = "running"
    mock_docker.containers.run.return_value = mock_c

    container = RealSupervisorContainer(
        api_url=f"http://host.docker.internal:{test_port}",
        data_root=tmp_path / "data",
        engine_cache=tmp_path / "engine",
        geoip_cache=tmp_path / "geoip",
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_url="ws://host.docker.internal",
        gateway_control_url=f"http://host.docker.internal:{DEFAULT_GATEWAY_PORT}",
        gateway_token_file=gw_token_file,
        prefix="test-thread",
        port=8005,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=mock_docker,
    )

    def slow_health_check(*args, **kwargs):
        time.sleep(0.3)
        resp = MagicMock()
        resp.status_code = 200
        return resp

    try:
        with patch("httpx.Client") as mock_client_cls:
            mock_http = MagicMock()
            mock_http.get.side_effect = slow_health_check
            mock_http.__enter__.return_value = mock_http
            mock_client_cls.return_value = mock_http

            start_task = asyncio.create_task(
                asyncio.to_thread(container.start, timeout_sec=2.0)
            )

            async with httpx.AsyncClient(trust_env=False) as async_c:
                res = await async_c.get(f"http://127.0.0.1:{test_port}/ping")
                assert res.status_code == 200
                assert res.text == "pong"
                assert ping_hit is True

            await start_task
    finally:
        await runner.cleanup()


def test_real_api_process_start_failure_reaps_child_and_closes_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RealApiProcess.start must reap child and close log on health timeout."""
    token_file = tmp_path / "token"
    token_file.write_text(secrets.token_hex(32))
    token_file.chmod(0o600)

    log_path = tmp_path / "api_test.log"
    api = RealApiProcess(
        port=get_free_port(),
        db_path=tmp_path / "dummy.db",
        token_file=token_file,
        root=tmp_path,
        env={},
        log_path=log_path,
    )

    sleep_cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    orig_popen = subprocess.Popen
    spawned_procs = []

    def fake_popen(*args, **kwargs):
        proc = orig_popen(sleep_cmd, stdout=kwargs.get("stdout"))
        spawned_procs.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, *a, **kw: httpx.Response(
            503, request=httpx.Request("GET", url)
        ),
    )

    try:
        with pytest.raises(TimeoutError):
            api.start(timeout_sec=0.2)

        assert len(spawned_procs) == 1
        reaped_proc = spawned_procs[0]
        assert reaped_proc.poll() is not None, "Child process must be reaped"
        assert api.log_handle_closed, "Log handle must be closed"
        assert api.proc is None
    finally:
        for p in spawned_procs:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=2)


def test_real_api_process_popen_error_closes_log_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Popen failure during start must close log handle and propagate original error."""
    token_file = tmp_path / "token"
    token_file.write_text(secrets.token_hex(32))
    token_file.chmod(0o600)

    log_path = tmp_path / "api_test.log"
    api = RealApiProcess(
        port=get_free_port(),
        db_path=tmp_path / "dummy.db",
        token_file=token_file,
        root=tmp_path,
        env={},
        log_path=log_path,
    )

    def broken_popen(*args, **kwargs):
        raise OSError("Simulated Popen spawn failure")

    monkeypatch.setattr(subprocess, "Popen", broken_popen)

    with pytest.raises(OSError, match="Simulated Popen spawn failure"):
        api.start(timeout_sec=0.2)

    assert api.proc is None
    assert api.log_handle_closed
    assert log_path.exists()


def test_real_api_process_stop_kill_wait_failure_propagates_and_retains_proc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RealApiProcess.stop propagates wait failure and retains proc reference."""
    token_file = tmp_path / "token"
    token_file.write_text(secrets.token_hex(32))
    token_file.chmod(0o600)

    log_path = tmp_path / "api_test.log"
    api = RealApiProcess(
        port=get_free_port(),
        db_path=tmp_path / "dummy.db",
        token_file=token_file,
        root=tmp_path,
        env={},
        log_path=log_path,
    )

    orig_popen = subprocess.Popen
    sleep_cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    log_handle = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    proc = orig_popen(sleep_cmd, stdout=log_handle, stderr=subprocess.STDOUT)
    api.proc = proc
    api._log_file_handle = log_handle

    def failing_wait(timeout=None):
        raise subprocess.TimeoutExpired(cmd=sleep_cmd, timeout=timeout or 2.0)

    monkeypatch.setattr(proc, "wait", failing_wait)

    try:
        with pytest.raises(subprocess.TimeoutExpired):
            api.stop(timeout_sec=0.01)

        assert api.proc is proc, "Unreaped process reference must be retained"
        assert api.log_handle_closed, "Log handle must be closed in finally"
        assert log_handle.closed is True, "Underlying log handle must be closed"
    finally:
        monkeypatch.undo()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2.0)


def test_real_api_process_start_failure_with_cleanup_failure_chains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Start health timeout with cleanup wait failure must chain stop_exc from exc."""
    token_file = tmp_path / "token"
    token_file.write_text(secrets.token_hex(32))
    token_file.chmod(0o600)

    log_path = tmp_path / "api_test.log"
    api = RealApiProcess(
        port=get_free_port(),
        db_path=tmp_path / "dummy.db",
        token_file=token_file,
        root=tmp_path,
        env={},
        log_path=log_path,
    )

    orig_popen = subprocess.Popen
    sleep_cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    spawned_procs = []

    def fake_popen(*args, **kwargs):
        p = orig_popen(
            sleep_cmd,
            stdout=kwargs.get("stdout"),
            stderr=kwargs.get("stderr"),
        )
        spawned_procs.append(p)

        def failing_wait(timeout=None):
            raise subprocess.TimeoutExpired(cmd=sleep_cmd, timeout=timeout or 2.0)

        monkeypatch.setattr(p, "wait", failing_wait)
        return p

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, *a, **kw: httpx.Response(
            503, request=httpx.Request("GET", url)
        ),
    )

    try:
        with pytest.raises(subprocess.TimeoutExpired) as exc_info:
            api.start(timeout_sec=0.1)

        assert isinstance(exc_info.value.__cause__, TimeoutError)
        assert api.proc is spawned_procs[0], (
            "Proc reference must be retained on cleanup error"
        )
        assert api.log_handle_closed, "Log handle must be closed in finally"
    finally:
        monkeypatch.undo()
        for p in spawned_procs:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=2.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_payload", ["null", "[]", "123", "true"])
async def test_production_gateway_forwards_non_dict_viewer_json(
    tmp_path: Path, bad_payload: str
) -> None:
    """Non-dict viewer JSON is forwarded and the production tunnel stays open."""
    key_file = tmp_path / "gw_agent_key"
    key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    key_file.chmod(0o600)
    token_file = tmp_path / "gw_token"
    token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    token_file.chmod(0o600)

    profile_id = "profile_signal"
    runtime_instance_id = "inst_signal"
    credentials = AgentCredentials(key_file)
    fake_api = FakeGatewayApiClient()
    fake_api.set_profile_runtime(profile_id, runtime_instance_id)
    fake_api.allow_all_viewers = True
    gateway = ProductionGatewayService(
        port=0,
        agent_key_file=key_file,
        gateway_token_file=token_file,
        api_client=fake_api,
    )
    server = TestServer(gateway.app)
    client = TestClient(server)
    await client.start_server()
    try:
        agent_token = credentials.token_for(profile_id, runtime_instance_id)
        register_url = (
            "/stream/agent/register"
            f"?profile_id={profile_id}&runtime_instance_id={runtime_instance_id}"
        )
        async with client.ws_connect(
            register_url, headers={"Authorization": f"Bearer {agent_token}"}
        ) as agent_ws:
            agent_config = SimpleNamespace(
                profile_id=profile_id,
                runtime_instance_id=runtime_instance_id,
                udp_mux_port=30000,
                selkies_version="2.1.0",
                config_version=1,
                video_streaming_mode=False,
                width=1920,
                height=1080,
            )
            register = build_register_envelope(
                agent_config,
                build_register_payload(agent_config, "test-host", "2.1.0"),
                iso_now(),
            )
            await agent_ws.send_str(register.model_dump_json())
            ack = await agent_ws.receive_json()
            assert ack["status"] == "ok"

            async with client.ws_connect(
                f"/stream/{profile_id}/signal",
                headers={
                    "Origin": "https://127.0.0.1:56661",
                    "Cookie": "cbrowser_session=test-session",
                },
            ) as viewer_ws:
                opened = await agent_ws.receive_json()
                assert opened["type"] == "open"

                await viewer_ws.send_str(bad_payload)
                forwarded = await agent_ws.receive_json()
                assert forwarded["type"] == "msg"
                assert forwarded["data"] == bad_payload
                assert not viewer_ws.closed

                await viewer_ws.close()
                close_env = await agent_ws.receive_json()
                assert close_env["type"] == "close"
    finally:
        await client.close()
