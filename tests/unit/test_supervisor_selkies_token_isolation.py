"""Selkies token directory isolation from the Browser sandbox (security finding)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import docker.errors
import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
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
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    leaked = dirs["runtime"] / "selkies_tokens.json"
    leaked.write_text("{}", encoding="utf-8")
    leaked.chmod(0o600)

    with pytest.raises(PathSecurityError, match="Secret source escapes"):
        adapter.validator.validate_secret_source("p1", leaked)


@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_stream_rejects_group_readable_agent_secret(tmp_path: Path) -> None:
    adapter, _mock_client, _ = _adapter(tmp_path)
    adapter.remember_profile_number("p1", 1)
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


# NOTE (t080): the two container-mount tests were removed wholesale because they asserted the
# pre-t080 host bind-mount `volumes` dict representation; ADR 029
# replaces it with typed named-volume subpath `mounts`.  The same
# scenarios are covered under the new representation by
# tests/unit/test_t080_adapter_mounts.py.

