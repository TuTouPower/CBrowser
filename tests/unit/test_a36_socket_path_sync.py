"""A36: container socket path helper and stream boundary fail-closed sync."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cbrowser.runtime_agent import socket_root as sr
from cbrowser.stream_agent import boundary

PROFILE = "prof_sync"
INSTANCE = "inst_sync"


def test_container_helper_matches_agent_socket_path(monkeypatch) -> None:
    monkeypatch.setenv(sr.AGENT_SOCKET_ROOT_ENV, "/run/cb/socks")
    monkeypatch.setenv("PROFILE_ID", PROFILE)
    monkeypatch.setenv("RUNTIME_INSTANCE_ID", INSTANCE)
    expected = sr.agent_socket_path(Path("/run/cb/socks"), PROFILE, INSTANCE)
    assert sr.container_agent_socket_path() == str(expected)


def test_container_helper_uses_default_root(monkeypatch) -> None:
    monkeypatch.delenv(sr.AGENT_SOCKET_ROOT_ENV, raising=False)
    monkeypatch.setenv("PROFILE_ID", PROFILE)
    monkeypatch.setenv("RUNTIME_INSTANCE_ID", INSTANCE)
    expected = sr.agent_socket_path(
        sr.DEFAULT_AGENT_SOCKET_ROOT, PROFILE, INSTANCE
    )
    assert sr.container_agent_socket_path() == str(expected)


def test_container_helper_derives_managed_slot(monkeypatch) -> None:
    monkeypatch.setenv(sr.AGENT_SOCKET_ROOT_ENV, "/run/cb/socks")
    monkeypatch.setenv("PROFILE_ID", PROFILE)
    monkeypatch.setenv("RUNTIME_INSTANCE_ID", INSTANCE)
    path = Path(sr.container_agent_socket_path())
    assert path.parent.name == sr.socket_slot(PROFILE, INSTANCE)
    assert path.name == sr.AGENT_SOCKET_NAME


@pytest.mark.parametrize("missing", ["PROFILE_ID", "RUNTIME_INSTANCE_ID"])
def test_container_helper_rejects_missing_identity(monkeypatch, missing) -> None:
    monkeypatch.setenv(sr.AGENT_SOCKET_ROOT_ENV, "/run/cb/socks")
    monkeypatch.setenv("PROFILE_ID", PROFILE)
    monkeypatch.setenv("RUNTIME_INSTANCE_ID", INSTANCE)
    monkeypatch.delenv(missing)
    with pytest.raises(sr.SocketRootError, match="identity"):
        sr.container_agent_socket_path()


def test_container_helper_honours_explicit_env_mapping() -> None:
    env = {
        sr.AGENT_SOCKET_ROOT_ENV: "/run/cb/custom",
        "PROFILE_ID": PROFILE,
        "RUNTIME_INSTANCE_ID": INSTANCE,
    }
    expected = sr.agent_socket_path(Path("/run/cb/custom"), PROFILE, INSTANCE)
    assert sr.container_agent_socket_path(env) == str(expected)


def test_stream_boundary_blacklists_new_socket_root() -> None:
    assert "/run/cb/socks" in boundary.PROHIBITED_PATHS


def test_stream_boundary_rejects_exposed_new_socket_root(monkeypatch) -> None:
    def fake_exists(self):
        return str(self) == "/run/cb/socks"

    monkeypatch.setattr(Path, "exists", fake_exists)
    with pytest.raises(boundary.SecurityError, match="Prohibited path"):
        boundary.verify_stream_runtime_boundaries()


def test_container_helper_prefers_explicit_agent_socket_path() -> None:
    explicit = "/run/cb/socks/0123456789abcdef0123/agent.sock"
    env = {sr.AGENT_SOCKET_PATH_ENV: explicit}
    assert sr.container_agent_socket_path(env) == explicit


def test_container_helper_explicit_path_needs_no_identity() -> None:
    explicit = "/run/cb/socks/0123456789abcdef0123/agent.sock"
    env = {
        sr.AGENT_SOCKET_PATH_ENV: explicit,
        sr.AGENT_SOCKET_ROOT_ENV: "/run/cb/socks",
    }
    assert sr.container_agent_socket_path(env) == explicit


def test_container_helper_rejects_explicit_path_outside_root() -> None:
    env = {
        sr.AGENT_SOCKET_ROOT_ENV: "/run/cb/socks",
        sr.AGENT_SOCKET_PATH_ENV: "/etc/agent.sock",
    }
    with pytest.raises(sr.SocketRootError):
        sr.container_agent_socket_path(env)


def test_container_helper_rejects_explicit_path_overlong() -> None:
    overlong = "/run/cb/socks/" + ("x" * 200) + "/agent.sock"
    env = {sr.AGENT_SOCKET_PATH_ENV: overlong}
    with pytest.raises(sr.SocketRootError):
        sr.container_agent_socket_path(env)


def test_container_helper_rejects_explicit_path_symlink(tmp_path: Path) -> None:
    root = tmp_path / "socks"
    slot = root / "slot"
    slot.mkdir(parents=True)
    real = slot / "real.sock"
    real.touch()
    link = slot / sr.AGENT_SOCKET_NAME
    link.symlink_to(real)
    env = {
        sr.AGENT_SOCKET_ROOT_ENV: str(root),
        sr.AGENT_SOCKET_PATH_ENV: str(link),
    }
    with pytest.raises(sr.SocketRootError):
        sr.container_agent_socket_path(env)


@pytest.mark.asyncio
async def test_browser_container_config_env_exposes_full_agent_socket_path(
    tmp_path: Path, monkeypatch
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from cbrowser.supervisor.docker_adapter import DockerAdapter
    from cbrowser.supervisor.path_validator import PathValidator

    monkeypatch.delenv(sr.AGENT_SOCKET_ROOT_ENV, raising=False)
    data_root = tmp_path / "data"
    (data_root / "engine_cache" / "geoip").mkdir(parents=True)
    socket_root = tmp_path / "socks"
    validator = PathValidator(data_root, socket_root=socket_root)
    image = "sha256:" + "a" * 64
    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=data_root / "engine_cache",
        docker_client=MagicMock(),
        browser_image=image,
        stream_image=image,
        policy_image=image,
    )
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=data_root / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._install_network_policy = MagicMock()
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["runtime"] / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": {}}), encoding="utf-8"
    )
    container = MagicMock()
    container.id = "cid"
    adapter.client.containers.run = MagicMock(return_value=container)
    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="i1",
        snapshot_json_path=dirs["runtime"] / "snapshot.json",
    )
    env = adapter.client.containers.run.call_args.kwargs["environment"]
    expected = str(sr.agent_socket_path(socket_root, "p1", "i1"))
    assert env[sr.AGENT_SOCKET_PATH_ENV] == expected
    assert env[sr.AGENT_SOCKET_ROOT_ENV] == str(socket_root)
    assert env["PROFILE_ID"] == "p1"
    assert env["RUNTIME_INSTANCE_ID"] == "i1"


@pytest.mark.asyncio
async def test_stream_container_config_env_exposes_full_agent_socket_path(
    tmp_path: Path, monkeypatch
) -> None:
    from unittest.mock import MagicMock

    import docker.errors
    from cbrowser.supervisor.docker_adapter import DockerAdapter
    from cbrowser.supervisor.path_validator import PathValidator
    from cbrowser.supervisor.selkies_tokens import SelkiesTokens

    monkeypatch.delenv(sr.AGENT_SOCKET_ROOT_ENV, raising=False)
    root = tmp_path / "data"
    engine = root / "engine_cache"
    (engine / "geoip").mkdir(parents=True)
    mock_client = MagicMock()
    mock_client.api.inspect_container.return_value = {
        "Config": {
            "Hostname": "b-host",
            "Labels": {"com.cbrowser.config-version": "1"},
        }
    }
    mock_client.containers.get.side_effect = docker.errors.NotFound("Not found")
    mock_client.containers.run.return_value = MagicMock()
    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=mock_client,
        browser_image="sha256:" + "a" * 64,
        stream_image="sha256:" + "b" * 64,
        policy_image="sha256:" + "a" * 64,
    )
    adapter._install_network_policy = MagicMock()
    adapter._resolved_endpoint = MagicMock(return_value=[("127.0.0.1", 18097)])
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=root / "gate")
    dirs = adapter.prepare_profile_directories("p2")
    (dirs["x11"] / "X99").touch()
    (dirs["runtime"] / "Xauthority").touch()
    secret_dir = adapter.validator.get_secret_dir("p2")
    secret_dir.mkdir(parents=True, exist_ok=True)
    agent_secret = secret_dir / "agent_secret.txt"
    agent_secret.write_text("agent_secret_test", encoding="utf-8")
    agent_secret.chmod(0o600)
    tokens_path = secret_dir / "selkies_tokens.json"
    SelkiesTokens.generate().write_credentials_file(tokens_path)
    await adapter.start_stream_container(
        profile_id="p2",
        runtime_instance_id="inst_stream",
        browser_container_name="cbrowser-p2-browser",
        udp_mux_port=30006,
        agent_secret_path=agent_secret,
        selkies_tokens_path=tokens_path,
    )
    env = mock_client.containers.run.call_args.kwargs["environment"]
    expected = str(
        sr.agent_socket_path(adapter.validator.socket_root, "p2", "inst_stream")
    )
    assert env[sr.AGENT_SOCKET_PATH_ENV] == expected
    assert env[sr.AGENT_SOCKET_ROOT_ENV] == str(adapter.validator.socket_root)
    assert env["PROFILE_ID"] == "p2"
    assert env["RUNTIME_INSTANCE_ID"] == "inst_stream"


def _capture_recovery_supervisor_run_kwargs(tmp_path: Path, monkeypatch) -> dict:
    from unittest.mock import MagicMock

    from supervisor_recovery_probe import offline_fixture as of

    engine_cache = tmp_path / "engine"
    geoip_cache = tmp_path / "geoip"
    engine_cache.mkdir()
    geoip_cache.mkdir()
    secrets = {}
    for name in ("token", "agent_key", "gw_token"):
        path = tmp_path / name
        path.write_text("k", encoding="utf-8")
        secrets[name] = path

    container = MagicMock()
    container.id = "cid"
    container.status = "running"
    client = MagicMock()
    client.containers.run.return_value = container

    http_client = MagicMock()
    http_client.__enter__.return_value = http_client
    http_client.__exit__.return_value = False
    http_client.get.return_value = MagicMock(status_code=200)
    monkeypatch.setattr(of.httpx, "Client", MagicMock(return_value=http_client))

    sup = of.RealSupervisorContainer(
        api_url="http://127.0.0.1:1",
        data_root=tmp_path / "data",
        engine_cache=engine_cache,
        geoip_cache=geoip_cache,
        token_file=secrets["token"],
        agent_key_file=secrets["agent_key"],
        gateway_url="",
        gateway_control_url="",
        gateway_token_file=secrets["gw_token"],
        prefix="a36",
        port=1,
        root=tmp_path,
        env={},
        log_path=tmp_path / "sup.log",
        docker_client=client,
        supervisor_image="sha256:" + "a" * 64,
    )
    sup.start(timeout_sec=2.0)
    return client.containers.run.call_args.kwargs


def test_recovery_supervisor_container_config_exposes_short_socket_root(
    tmp_path: Path, monkeypatch
) -> None:
    kwargs = _capture_recovery_supervisor_run_kwargs(tmp_path, monkeypatch)
    assert kwargs["environment"][sr.AGENT_SOCKET_ROOT_ENV] == (
        sr.DEFAULT_AGENT_SOCKET_ROOT
    )
    assert kwargs["volumes"][sr.DEFAULT_AGENT_SOCKET_ROOT] == {
        "bind": sr.DEFAULT_AGENT_SOCKET_ROOT,
        "mode": "rw",
    }
    assert kwargs["read_only"] is True


def test_recovery_supervisor_socket_root_keeps_agent_socket_path_bounded(
    tmp_path: Path, monkeypatch
) -> None:
    from unittest.mock import MagicMock

    from cbrowser.supervisor.docker_adapter import DockerAdapter
    from cbrowser.supervisor.path_validator import PathValidator

    kwargs = _capture_recovery_supervisor_run_kwargs(tmp_path, monkeypatch)
    root = kwargs["environment"][sr.AGENT_SOCKET_ROOT_ENV]
    monkeypatch.setenv(sr.AGENT_SOCKET_ROOT_ENV, root)

    data_root = tmp_path / "deep_persistent_data_root" / "data"
    (data_root / "engine_cache" / "geoip").mkdir(parents=True)
    validator = PathValidator(data_root)
    image = "sha256:" + "a" * 64
    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=data_root / "engine_cache",
        docker_client=MagicMock(),
        browser_image=image,
        stream_image=image,
        policy_image=image,
    )
    env = adapter._agent_socket_environment(PROFILE, INSTANCE)
    assert set(env) == {
        sr.AGENT_SOCKET_ROOT_ENV,
        sr.AGENT_SOCKET_PATH_ENV,
        "PROFILE_ID",
        "RUNTIME_INSTANCE_ID",
    }
    expected = str(sr.agent_socket_path(Path(root), PROFILE, INSTANCE))
    assert env[sr.AGENT_SOCKET_PATH_ENV] == expected
    assert len(os.fsencode(env[sr.AGENT_SOCKET_PATH_ENV])) <= sr.SUN_PATH_BYTE_LIMIT
    assert sr.container_agent_socket_path(env) == expected
