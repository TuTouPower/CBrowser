"""A11: network policy helper timeouts stay redacted and fail-closed."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator
from docker.errors import DockerException

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"
SECRET = "http://unix/var/run/docker.sock/SECRET-TOKEN-1234"


class _Helper:
    def __init__(self, *, wait_error=None, status=0, remove_error=None):
        self.wait_error = wait_error
        self.status = status
        self.remove_error = remove_error
        self.removed = False

    def wait(self, timeout=None):
        if self.wait_error is not None:
            raise self.wait_error
        return {"StatusCode": self.status}

    def remove(self, force=False):
        if self.remove_error is not None:
            raise self.remove_error
        self.removed = True


def _adapter(tmp_path, helper):
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    client = SimpleNamespace(
        containers=SimpleNamespace(run=lambda *a, **kw: helper)
    )
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )


def _call(adapter, gate):
    adapter._install_network_policy(
        SimpleNamespace(id="target-id"),
        {
            "role": "stream",
            "allowed_tcp": [],
            "allowed_udp": [],
            "udp_mux_port": 30005,
        },
        gate,
        "inst1",
        "stream",
    )


def _gate(tmp_path):
    gate = tmp_path / "gate"
    gate.mkdir()
    return gate


def test_requests_read_timeout_is_redacted_sandbox_error(tmp_path):
    helper = _Helper(
        wait_error=requests.exceptions.ReadTimeout(SECRET),
    )
    adapter = _adapter(tmp_path, helper)
    gate = _gate(tmp_path)

    with pytest.raises(DockerSandboxError) as caught:
        _call(adapter, gate)
    assert SECRET not in str(caught.value)
    assert not (gate / "ready.json").exists()
    assert helper.removed is True


def test_requests_connection_error_is_redacted_sandbox_error(tmp_path):
    helper = _Helper(
        wait_error=requests.exceptions.ConnectionError(SECRET),
    )
    adapter = _adapter(tmp_path, helper)
    gate = _gate(tmp_path)

    with pytest.raises(DockerSandboxError) as caught:
        _call(adapter, gate)
    assert SECRET not in str(caught.value)
    assert not (gate / "ready.json").exists()
    assert helper.removed is True


def test_docker_exception_is_not_masked_by_cleanup_failure(tmp_path):
    helper = _Helper(
        wait_error=DockerException("daemon down"),
        remove_error=DockerException("cleanup broke"),
    )
    adapter = _adapter(tmp_path, helper)
    gate = _gate(tmp_path)

    with pytest.raises(DockerSandboxError) as caught:
        _call(adapter, gate)
    assert "cleanup broke" not in str(caught.value)
    assert "daemon down" not in str(caught.value)
    assert not (gate / "ready.json").exists()


def test_helper_remove_failure_keeps_gate_closed(tmp_path):
    helper = _Helper(remove_error=DockerException("cleanup broke"))
    adapter = _adapter(tmp_path, helper)
    gate = _gate(tmp_path)

    with pytest.raises(DockerSandboxError):
        _call(adapter, gate)
    assert not (gate / "ready.json").exists()


def test_failed_policy_exit_never_writes_ready(tmp_path):
    helper = _Helper(status=1)
    adapter = _adapter(tmp_path, helper)
    gate = _gate(tmp_path)

    with pytest.raises(DockerSandboxError):
        _call(adapter, gate)
    assert not (gate / "ready.json").exists()
    assert helper.removed is True


def test_successful_install_writes_ready_and_reclaims_helper(tmp_path):
    helper = _Helper(status=0)
    adapter = _adapter(tmp_path, helper)
    gate = _gate(tmp_path)

    _call(adapter, gate)
    assert (gate / "ready.json").exists()
    assert helper.removed is True
