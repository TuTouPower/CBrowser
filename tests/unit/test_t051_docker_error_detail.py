"""t051 AC-011/p059: sandbox start failures keep the Docker root cause.

Previously ``start_stream_container`` (and the cache/X11/policy/network
helpers) kept only ``type(exc).__name__``, while ``start_browser_container``
spliced the raw exception without redaction.  Every site below must now
carry the Docker error's own text, redacted through the shared rules, so
a port conflict or bad image parameter is diagnosable from the log while
proxy credentials, URL userinfo and tokens never leak.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cbrowser.supervisor.docker_adapter import (
    DockerAdapter,
    DockerSandboxError,
    StreamContainerResidueError,
)
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.selkies_tokens import SelkiesTokens
from docker.errors import APIError, DockerException, NotFound

BROWSER = "sha256:" + "a" * 64
STREAM = "sha256:" + "b" * 64

# A Docker error carrying both a diagnosable root cause and secrets that
# must never reach the exception text or the log.
DETAIL = (
    "400 Client Error: Bind for 0.0.0.0:30006 failed: port is already "
    "allocated (proxy http://proxy-user:s3cret@proxy.example:8080)"
)


def _adapter(tmp_path: Path, client) -> DockerAdapter:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )


def _fake_helper(status_code: int = 0) -> MagicMock:
    helper = MagicMock()
    helper.wait.return_value = {"StatusCode": status_code}
    return helper


@pytest.mark.asyncio
async def test_browser_start_failure_keeps_docker_detail_redacted(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=tmp_path / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._resolved_endpoint = MagicMock(return_value=[])
    adapter._install_network_policy = MagicMock()
    adapter.remember_profile_number("p1", 1)

    dirs = adapter.prepare_profile_directories("p1")
    (dirs["runtime"] / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": {}}), encoding="utf-8"
    )
    client.containers.run.side_effect = DockerException(DETAIL)

    with pytest.raises(DockerSandboxError) as caught:
        await adapter.start_browser_container(
            profile_id="p1",
            runtime_instance_id="inst_1",
            snapshot_json_path=dirs["runtime"] / "snapshot.json",
        )
    message = str(caught.value)
    assert "30006" in message and "already allocated" in message
    assert "proxy-user" not in message and "s3cret" not in message
    assert "http://<redacted>@proxy.example:8080" in message


@pytest.mark.asyncio
async def test_stream_start_failure_keeps_docker_detail_redacted(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    adapter.remember_profile_number("p1", 1)
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
    client.api.inspect_container.return_value = {
        "Config": {
            "Hostname": "b-host",
            "Labels": {"com.cbrowser.config-version": "1"},
        }
    }
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=tmp_path / "gate")
    client.containers.run.side_effect = DockerException(DETAIL)

    with pytest.raises(DockerSandboxError) as caught:
        await adapter.start_stream_container(
            profile_id="p1",
            runtime_instance_id="inst_1",
            browser_container_name="cbrowser-p1-browser",
            udp_mux_port=30006,
            agent_secret_path=agent_secret,
            selkies_tokens_path=tokens_path,
        )
    message = str(caught.value)
    assert "30006" in message and "already allocated" in message
    assert "proxy-user" not in message and "s3cret" not in message
    assert "DockerException" not in message


@pytest.mark.asyncio
async def test_stream_residue_error_keeps_docker_detail(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    adapter.remember_profile_number("p1", 1)
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
    client.api.inspect_container.return_value = {
        "Config": {
            "Hostname": "b-host",
            "Labels": {"com.cbrowser.config-version": "1"},
        }
    }
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=tmp_path / "gate")
    container = MagicMock()
    container.id = "stream-container-id"
    container.name = adapter.get_stream_container_name("p1")
    container.remove = MagicMock(side_effect=DockerException("remove failed"))
    container.labels = {
        "com.cbrowser.prefix": adapter.resource_prefix,
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "stream",
        "com.cbrowser.profile-id": "p1",
        "com.cbrowser.instance-id": "inst_1",
    }
    client.containers.run.return_value = container
    adapter._resolved_endpoint = MagicMock(
        side_effect=DockerException(
            "500 Server Error: proxy http://proxy-user:s3cret@proxy:8080 refused"
        )
    )

    with pytest.raises(StreamContainerResidueError) as caught:
        await adapter.start_stream_container(
            profile_id="p1",
            runtime_instance_id="inst_1",
            browser_container_name="cbrowser-p1-browser",
            udp_mux_port=30006,
            agent_secret_path=agent_secret,
            selkies_tokens_path=tokens_path,
        )
    assert caught.value.cause_type == "DockerException"
    assert "proxy-user" not in str(caught.value)
    assert "s3cret" not in str(caught.value)
    assert "proxy:8080" in str(caught.value)


def test_cache_initializer_failure_keeps_docker_detail(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    client.containers.run.side_effect = DockerException(
        "image pull failed: unauthorized for sha256:deadbeef"
    )
    with pytest.raises(DockerSandboxError) as caught:
        adapter._initialize_cache(False)
    assert "unauthorized" in str(caught.value)
    assert "sha256:deadbeef" in str(caught.value)


def test_x11_helper_failure_keeps_docker_detail(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    client.containers.run.side_effect = DockerException(
        "permission denied while trying to connect to the Docker daemon"
    )
    with pytest.raises(DockerSandboxError) as caught:
        adapter.setup_x11_permissions(tmp_path / "x11")
    assert "permission denied" in str(caught.value)


def test_network_create_failure_keeps_docker_detail_without_retry(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    client.networks.get.side_effect = NotFound("no such network")
    client.networks.create.side_effect = DockerException(
        "network cbrowser-media-p1 already exists with another subnet"
    )
    with pytest.raises(DockerSandboxError) as caught:
        adapter._ensure_network("p1", "cbrowser-media-p1")
    assert "already exists" in str(caught.value)
    assert client.networks.create.call_count == 1


def test_media_network_conflict_is_an_error_not_a_retry(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    client.networks.get.side_effect = NotFound("no such network")
    client.networks.list.return_value = []
    client.networks.create.side_effect = APIError(
        "Pool overlaps with other one on this address space"
    )
    with pytest.raises(DockerSandboxError) as caught:
        adapter._ensure_media_network("p1")
    assert "overlaps" in str(caught.value)
    assert client.networks.create.call_count == 1


def test_network_list_failure_keeps_docker_detail(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    client.networks.list.side_effect = DockerException(
        "Error while fetching server API version: connection reset"
    )
    with pytest.raises(DockerSandboxError) as caught:
        adapter._used_subnets()
    assert "connection reset" in str(caught.value)


def test_policy_install_failure_keeps_docker_detail_redacted(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    gate = adapter._prepare_policy_gate("p1", "inst_1", "browser")
    client.containers.create.side_effect = DockerException(
        "iptables failed: proxy http://proxy-user:s3cret@proxy:8080"
    )
    container = SimpleNamespace(id="browser-id", labels={})
    with pytest.raises(DockerSandboxError) as caught:
        adapter._install_network_policy(
            container, {"role": "browser", "allowed_tcp": []}, gate, "inst_1", "browser"
        )
    message = str(caught.value)
    assert "iptables failed" in message
    assert "proxy-user" not in message and "s3cret" not in message


def test_policy_helper_run_failure_keeps_docker_detail(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    client.containers.create.side_effect = DockerException(
        "helper image not found: no such image sha256:deadbeef"
    )
    container = SimpleNamespace(id="browser-id", labels={})
    with pytest.raises(DockerSandboxError) as caught:
        adapter._run_policy_helper(container, ["iptables", "-L"])
    assert "no such image" in str(caught.value)


def test_media_network_inspect_failure_keeps_docker_detail(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    client.networks.get.side_effect = DockerException(
        "failed to inspect network: network is in use by container"
    )
    with pytest.raises(DockerSandboxError) as caught:
        adapter.inspect_media_network("p1")
    assert "network is in use" in str(caught.value)
