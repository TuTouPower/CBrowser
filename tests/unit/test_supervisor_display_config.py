"""Supervisor passes the bound config version's screen geometry to Stream."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import docker.errors
import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.selkies_tokens import SelkiesTokens

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def _adapter(tmp_path: Path) -> tuple[DockerAdapter, dict[str, Path], Path]:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    mock_client = MagicMock()
    mock_client.api.inspect_container.return_value = {
        "Config": {
            "Hostname": "b-host",
            "Labels": {"com.cbrowser.config-version": "3"},
        }
    }
    mock_client.containers.get.side_effect = docker.errors.NotFound("Not found")
    mock_container = MagicMock()
    mock_container.name = "t007-display-stream"
    mock_client.containers.run.return_value = mock_container

    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=mock_client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )
    adapter._install_network_policy = MagicMock()
    adapter._resolved_endpoint = MagicMock(return_value=[("127.0.0.1", 18097)])
    adapter.remember_profile_number("p2", 1)
    dirs = adapter.prepare_profile_directories("p2")
    (dirs["x11"] / "X99").touch()
    (dirs["runtime"] / "Xauthority").touch()
    return adapter, dirs, mock_client


def _write_snapshot(path: Path, config: dict) -> Path:
    path.write_text(
        json.dumps(
            {
                "id": "snap_display",
                "profile_id": "p2",
                "version": 3,
                "config": config,
                "created_at": "2026-10-31T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o644)
    return path


async def _start(
    adapter: DockerAdapter,
    dirs: dict[str, Path],
    snapshot: Path | None,
) -> dict:
    secret_dir = adapter.validator.get_secret_dir("p2")
    secret_dir.mkdir(parents=True, exist_ok=True)
    agent_secret = secret_dir / "agent_secret.txt"
    agent_secret.write_text("agent_secret_test", encoding="utf-8")
    agent_secret.chmod(0o600)
    tokens = SelkiesTokens.generate()
    tokens_path = secret_dir / "selkies_tokens.json"
    tokens.write_credentials_file(tokens_path)

    await adapter.start_stream_container(
        profile_id="p2",
        runtime_instance_id="inst_display",
        browser_container_name="cbrowser-p2-browser",
        udp_mux_port=30006,
        agent_secret_path=agent_secret,
        selkies_tokens_path=tokens_path,
        snapshot_json_path=snapshot,
    )
    return adapter.client.containers.run.call_args.kwargs


@pytest.mark.asyncio
async def test_stream_env_uses_bound_snapshot_geometry(tmp_path: Path) -> None:
    adapter, dirs, _ = _adapter(tmp_path)
    snapshot = _write_snapshot(
        dirs["runtime"] / "snapshot.json",
        {"screen_width": 1280, "screen_height": 720},
    )

    call_kwargs = await _start(adapter, dirs, snapshot)
    env = call_kwargs["environment"]

    assert env["CBROWSER_SCREEN_WIDTH"] == "1280"
    assert env["CBROWSER_SCREEN_HEIGHT"] == "720"


@pytest.mark.asyncio
async def test_stream_start_fails_when_snapshot_geometry_missing(
    tmp_path: Path,
) -> None:
    adapter, dirs, _ = _adapter(tmp_path)
    snapshot = _write_snapshot(dirs["runtime"] / "snapshot.json", {})

    with pytest.raises(DockerSandboxError, match="screen_width"):
        await _start(adapter, dirs, snapshot)


@pytest.mark.asyncio
async def test_stream_start_fails_when_snapshot_missing(tmp_path: Path) -> None:
    adapter, dirs, _ = _adapter(tmp_path)

    with pytest.raises(Exception, match="snapshot"):
        await _start(adapter, dirs, dirs["runtime"] / "missing.json")
