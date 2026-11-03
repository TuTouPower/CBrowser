"""Unit tests for Selkies token generation, permissions, and mounts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.selkies_tokens import SelkiesTokens

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def test_selkies_tokens_randomness_and_uniqueness() -> None:
    t1 = SelkiesTokens.generate()
    t2 = SelkiesTokens.generate()

    assert t1.master_token != t2.master_token
    assert t1.controller_token != t2.controller_token
    assert t1.master_token != t1.controller_token

    # 32 bytes urlsafe is 43 or 44 base64 chars
    assert len(t1.master_token) >= 42
    assert len(t1.controller_token) >= 42
    assert isinstance(t1.master_token, str)
    assert isinstance(t1.controller_token, str)


def test_selkies_tokens_write_credentials_file_0600(tmp_path: Path) -> None:
    tokens = SelkiesTokens.generate()
    target = tmp_path / "selkies_tokens.json"

    tokens.write_credentials_file(target)

    assert target.is_file()
    # File permissions must be 0600 (owner rw only, group and other must be 0)
    mode = target.stat().st_mode & 0o777
    assert mode == 0o600

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["master_token"] == tokens.master_token
    assert data["controller_token"] == tokens.controller_token


@pytest.mark.asyncio
async def test_start_stream_container_requires_selkies_tokens_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    validator = PathValidator(root)
    mock_client = MagicMock()

    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine,
        docker_client=mock_client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )

    dirs = adapter.prepare_profile_directories("p1")
    (dirs["x11"] / "X99").touch()
    (dirs["runtime"] / "Xauthority").touch()
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    agent_secret = secret_dir / "agent_secret.txt"
    agent_secret.write_text("agent_secret_test", encoding="utf-8")
    agent_secret.chmod(0o600)

    expected_msg = "Explicit Stream Selkies token credential file is required"
    # 1. Missing selkies_tokens_path argument -> raises DockerSandboxError
    with pytest.raises(DockerSandboxError, match=expected_msg):
        await adapter.start_stream_container(
            profile_id="p1",
            runtime_instance_id="r1",
            browser_container_name="cbrowser-p1-browser",
            udp_mux_port=30006,
            agent_secret_path=agent_secret,
            selkies_tokens_path=None,
        )

    # 2. Path points to non-existent file -> raises DockerSandboxError
    non_existent = root / "runtime" / "p1" / "non_existent.json"
    with pytest.raises(DockerSandboxError, match=expected_msg):
        await adapter.start_stream_container(
            profile_id="p1",
            runtime_instance_id="r1",
            browser_container_name="cbrowser-p1-browser",
            udp_mux_port=30006,
            agent_secret_path=agent_secret,
            selkies_tokens_path=non_existent,
        )


@pytest.mark.asyncio
async def test_start_stream_container_enforces_0600_permissions(tmp_path: Path) -> None:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    validator = PathValidator(root)
    mock_client = MagicMock()

    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine,
        docker_client=mock_client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )

    dirs = adapter.prepare_profile_directories("p1")
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    agent_secret = secret_dir / "agent_secret.txt"
    agent_secret.write_text("agent_secret_test", encoding="utf-8")
    agent_secret.chmod(0o600)

    tokens_path = dirs["runtime"] / "selkies_tokens.json"
    tokens_path.write_text("{}", encoding="utf-8")

    # Insecure permission 0o644 (group/other readable) -> must be rejected
    tokens_path.chmod(0o644)
    with pytest.raises(DockerSandboxError, match="must have 0600 permissions"):
        await adapter.start_stream_container(
            profile_id="p1",
            runtime_instance_id="r1",
            browser_container_name="cbrowser-p1-browser",
            udp_mux_port=30006,
            agent_secret_path=agent_secret,
            selkies_tokens_path=tokens_path,
        )

    # Insecure permission 0o664 -> must be rejected
    tokens_path.chmod(0o664)
    with pytest.raises(DockerSandboxError, match="must have 0600 permissions"):
        await adapter.start_stream_container(
            profile_id="p1",
            runtime_instance_id="r1",
            browser_container_name="cbrowser-p1-browser",
            udp_mux_port=30006,
            agent_secret_path=agent_secret,
            selkies_tokens_path=tokens_path,
        )


@pytest.mark.asyncio
async def test_start_stream_container_mounts_tokens_file_readonly(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    validator = PathValidator(root)
    mock_client = MagicMock()

    mock_client.api.inspect_container.return_value = {
        "Config": {
            "Hostname": "b-host",
            "Labels": {"com.cbrowser.config-version": "1"},
        }
    }
    import docker.errors

    mock_client.containers.get.side_effect = docker.errors.NotFound("Not found")
    mock_container = MagicMock()
    mock_container.name = "t007-stream-tokens-stream-test"
    mock_client.containers.run.return_value = mock_container

    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine,
        docker_client=mock_client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )

    dirs = adapter.prepare_profile_directories("p1")
    (dirs["x11"] / "X99").touch()
    (dirs["runtime"] / "Xauthority").touch()
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    agent_secret = secret_dir / "agent_secret.txt"
    agent_secret.write_text("agent_secret_test", encoding="utf-8")
    agent_secret.chmod(0o600)

    tokens = SelkiesTokens.generate()
    tokens_path = secret_dir / "selkies_tokens.json"
    tokens.write_credentials_file(tokens_path)

    # Patch network policy and policy gate helpers
    adapter._install_network_policy = MagicMock()
    adapter._resolved_endpoint = MagicMock(return_value=[("127.0.0.1", 18097)])

    await adapter.start_stream_container(
        profile_id="p1",
        runtime_instance_id="r1",
        browser_container_name="cbrowser-p1-browser",
        udp_mux_port=30006,
        agent_secret_path=agent_secret,
        selkies_tokens_path=tokens_path,
    )

    call_kwargs = mock_client.containers.run.call_args.kwargs
    volumes = call_kwargs["volumes"]
    env = call_kwargs["environment"]

    assert str(tokens_path) in volumes
    assert volumes[str(tokens_path)] == {
        "bind": "/tmp/selkies_credentials.json",
        "mode": "ro",
    }
    assert env["CBROWSER_SELKIES_CREDENTIALS_FILE"] == "/tmp/selkies_credentials.json"


@pytest.mark.asyncio
async def test_supervisor_core_start_profile_provisions_selkies_tokens(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    validator = PathValidator(root)
    dirs = {
        "profile": root / "profiles" / "p1",
        "runtime": root / "runtime" / "p1",
        "events": root / "events" / "p1",
        "exchange": root / "exchange" / "p1",
        "x11": root / "runtime" / "p1" / "x11",
        "pulse": root / "runtime" / "p1" / "pulse",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    key_file = tmp_path / "agent_key"
    key_file.write_text("01234567890123456789012345678901", encoding="utf-8")
    key_file.chmod(0o600)

    mock_stream_c = MagicMock()
    mock_stream_c.id = "s_id"
    mock_stream_c.name = "stream_c"
    mock_stream_c.status = "running"
    mock_stream_c.reload = MagicMock()

    mock_browser_c = MagicMock()
    mock_browser_c.id = "b_id"
    mock_browser_c.name = "browser_c"

    def write_runner_info(profile_id, runtime_instance_id, snapshot_json_path):
        (dirs["runtime"] / "x11" / "X99").touch()
        (dirs["runtime"] / "pulse" / "pulse.sock").touch()
        (dirs["runtime"] / "Xauthority").touch()
        (dirs["runtime"] / "agent.sock").touch()
        runner_info = dirs["runtime"] / "runner_info.json"
        runner_info.write_text(
            json.dumps(
                {
                    "profile_id": profile_id,
                    "runtime_instance_id": runtime_instance_id,
                    "config_version": 1,
                    "browser_pid": 12345,
                }
            ),
            encoding="utf-8",
        )
        return mock_browser_c

    adapter = SimpleNamespace(
        validator=validator,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        attach_profile_infrastructure=MagicMock(return_value={}),
        start_browser_container=AsyncMock(side_effect=write_runner_info),
        start_stream_container=AsyncMock(return_value=mock_stream_c),
        teardown_profile=AsyncMock(),
        cleanup_profile_processes=MagicMock(),
        ensure_runtime_cache=AsyncMock(),
    )

    (dirs["runtime"] / "agent.sock").touch()

    events = SimpleNamespace(
        drain_runtime_events=AsyncMock(return_value=0),
        forward_exit_event=AsyncMock(),
        emit_event=AsyncMock(),
    )
    ports = PortAllocator(30000, 30010)

    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={"status": "ok", "desired_state": "running", "restart_blocked": False},
        )
    )

    mock_gw = SimpleNamespace(
        has_foreground_viewers=AsyncMock(return_value=True),
        disconnect_viewers=AsyncMock(),
    )

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test-api"
    ) as api:
        core = SupervisorCore(
            docker_adapter=adapter,
            port_allocator=ports,
            event_forwarder=events,
            api_client=api,
            gateway_url="ws://supervisor-host-gw:18097",
            token_file=None,
            agent_key_file=key_file,
            gateway_control=mock_gw,
        )

        session = await core.start_profile("p1", ProfileConfig(name="p1"))

        # Verify the per-instance credentials file is 0600 and outside runtime
        call_kwargs = adapter.start_stream_container.call_args.kwargs
        tokens_file = call_kwargs["selkies_tokens_path"]
        assert tokens_file.parent == validator.get_secret_dir("p1")
        assert tokens_file.name == f"selkies_tokens_{session.runtime_instance_id}.json"
        assert not tokens_file.is_relative_to(dirs["runtime"])
        assert tokens_file.is_file()
        assert (tokens_file.stat().st_mode & 0o777) == 0o600

        data = json.loads(tokens_file.read_text(encoding="utf-8"))
        assert "master_token" in data
        assert "controller_token" in data
        assert len(data["master_token"]) >= 42

        # Verify session and attributes do not leak master_token
        session_dict = vars(session)
        assert data["master_token"] not in str(session_dict)
