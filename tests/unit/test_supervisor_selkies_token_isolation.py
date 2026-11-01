"""Selkies token directory isolation from the Browser sandbox (security finding)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import docker.errors
import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.docker_adapter import DockerSandboxError
from cbrowser.supervisor.path_validator import PathSecurityError, PathValidator
from cbrowser.supervisor.selkies_tokens import SelkiesTokens

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def _adapter(tmp_path: Path) -> tuple[DockerAdapter, MagicMock, Path]:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    mock_client = MagicMock()
    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=mock_client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )
    return adapter, mock_client, root


def test_profile_secret_directory_is_not_the_browser_mounted_runtime_dir(
    tmp_path: Path,
) -> None:
    adapter, _, _ = _adapter(tmp_path)
    runtime_dir = adapter.validator.get_runtime_dir("p1")
    secret_dir = adapter.validator.get_secret_dir("p1")

    assert secret_dir != runtime_dir
    assert not secret_dir.is_relative_to(runtime_dir)
    assert secret_dir.is_relative_to(adapter.validator.data_root)


def test_secret_validation_rejects_files_inside_browser_runtime_dir(
    tmp_path: Path,
) -> None:
    adapter, _, _ = _adapter(tmp_path)
    dirs = adapter.prepare_profile_directories("p1")
    leaked = dirs["runtime"] / "selkies_tokens.json"
    leaked.write_text("{}", encoding="utf-8")
    leaked.chmod(0o600)

    with pytest.raises(PathSecurityError, match="Secret source escapes"):
        adapter.validator.validate_secret_source("p1", leaked)


@pytest.mark.asyncio
async def test_browser_container_mounts_never_include_secret_directory(
    tmp_path: Path,
) -> None:
    adapter, mock_client, _ = _adapter(tmp_path)
    dirs = adapter.prepare_profile_directories("p1")
    snapshot_path = dirs["runtime"] / "snapshot.json"
    snapshot_path.write_text(json.dumps({"version": 1, "config": {}}), encoding="utf-8")

    mock_client.containers.run.return_value = MagicMock()
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=tmp_path / "browser_gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._resolved_endpoint = MagicMock(return_value=[])
    adapter._install_network_policy = MagicMock()

    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        snapshot_json_path=snapshot_path,
    )

    volumes = mock_client.containers.run.call_args.kwargs["volumes"]
    secret_dir = adapter.validator.get_secret_dir("p1")

    assert str(dirs["runtime"]) in volumes
    assert str(secret_dir) not in volumes
    for source in volumes:
        source_path = Path(source)
        assert not source_path.is_relative_to(secret_dir)
        assert not secret_dir.is_relative_to(source_path)


@pytest.mark.asyncio
async def test_stream_container_mounts_token_from_secret_directory(
    tmp_path: Path,
) -> None:
    adapter, mock_client, _ = _adapter(tmp_path)
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["x11"] / "X99").touch()
    (dirs["runtime"] / "Xauthority").touch()

    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    agent_secret = secret_dir / "agent_secret.txt"
    agent_secret.write_text("agent_secret_test", encoding="utf-8")
    agent_secret.chmod(0o600)
    tokens_path = secret_dir / "selkies_tokens.json"
    SelkiesTokens.generate().write_credentials_file(tokens_path)

    mock_client.api.inspect_container.return_value = {
        "Config": {
            "Hostname": "b-host",
            "Labels": {"com.cbrowser.config-version": "1"},
        }
    }
    mock_client.containers.get.side_effect = docker.errors.NotFound("Not found")
    mock_client.containers.run.return_value = MagicMock()

    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=tmp_path / "stream_gate")
    adapter._resolved_endpoint = MagicMock(return_value=[("127.0.0.1", 18097)])
    adapter._install_network_policy = MagicMock()

    await adapter.start_stream_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        browser_container_name="cbrowser-p1-browser",
        udp_mux_port=30006,
        agent_secret_path=agent_secret,
        selkies_tokens_path=tokens_path,
    )

    call_kwargs = mock_client.containers.run.call_args.kwargs
    volumes = call_kwargs["volumes"]

    assert str(tokens_path) in volumes
    assert volumes[str(tokens_path)] == {
        "bind": "/tmp/selkies_credentials.json",
        "mode": "ro",
    }
    assert volumes[str(agent_secret)] == {"bind": "/tmp/secret.txt", "mode": "ro"}
    assert not tokens_path.is_relative_to(dirs["runtime"])
    assert not agent_secret.is_relative_to(dirs["runtime"])


@pytest.mark.asyncio
async def test_stream_rejects_group_readable_agent_secret(tmp_path: Path) -> None:
    adapter, mock_client, _ = _adapter(tmp_path)
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["x11"] / "X99").touch()
    (dirs["runtime"] / "Xauthority").touch()
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    agent_secret = secret_dir / "agent_secret.txt"
    agent_secret.write_text("agent_secret_test", encoding="utf-8")
    agent_secret.chmod(0o644)
    tokens_path = secret_dir / "selkies_tokens.json"
    SelkiesTokens.generate().write_credentials_file(tokens_path)

    with pytest.raises(DockerSandboxError, match="must have 0600"):
        await adapter.start_stream_container(
            profile_id="p1",
            runtime_instance_id="inst_1",
            browser_container_name="cbrowser-p1-browser",
            udp_mux_port=30006,
            agent_secret_path=agent_secret,
            selkies_tokens_path=tokens_path,
        )
