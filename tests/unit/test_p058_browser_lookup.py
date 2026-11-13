"""p058: Browser container lookup is ownership-filtered and fence-aware.

Candidates are filtered by ownership labels (including the deployment
identity, com.cbrowser.instance-id, when configured); the per-launch
runtime instance is matched from each candidate's runtime
configuration, never from labels.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


def _container(instance: str, status: str = "running") -> SimpleNamespace:
    # Mirrors a production Browser container: the runtime instance id is
    # carried by the gated entrypoint / command in the configuration.
    return SimpleNamespace(
        status=status,
        labels={
            "com.cbrowser.prefix": "cb",
            "com.cbrowser.profile-id": "p1",
            "com.cbrowser.role": "browser",
        },
        attrs={
            "Config": {
                "Entrypoint": [
                    "python3",
                    "-m",
                    "cbrowser.supervisor.gated_entrypoint",
                    "--instance-id",
                    instance,
                    "--role",
                    "browser",
                ],
                "Cmd": ["--runtime-instance-id", instance],
            }
        },
    )


class _Client:
    def __init__(self, containers=None, error=None):
        self._containers = containers or []
        self._error = error
        self.filters = None
        self.containers = self

    def list(self, *, all=False, filters=None):
        self.filters = filters
        if self._error is not None:
            raise self._error
        return self._containers


def _core(tmp_path, client: _Client) -> SupervisorCore:
    docker = SimpleNamespace(
        validator=PathValidator(tmp_path / "data"),
        resource_prefix="cb",
        deployment_instance_id=None,
        client=SimpleNamespace(containers=client),
    )
    api = httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
    )
    return SupervisorCore(
        docker, PortAllocator(), EventForwarder("http://api.invalid", tmp_path / "spool", client=api), api
    )


@pytest.mark.asyncio
async def test_found_uses_matching_instance_not_first_container(tmp_path):
    client = _Client([_container("other"), _container("inst1")])
    core = _core(tmp_path, client)

    lookup = await core._lookup_browser_container("p1", "inst1")

    assert lookup.outcome == "found"
    assert lookup.container_status == "running"
    labels = client.filters["label"]
    assert "com.cbrowser.profile-id=p1" in labels
    assert "com.cbrowser.role=browser" in labels


@pytest.mark.asyncio
async def test_other_instance_is_a_fence_mismatch(tmp_path):
    core = _core(tmp_path, _Client([_container("other")]))

    lookup = await core._lookup_browser_container("p1", "inst1")

    assert lookup.outcome == "instance_mismatch"
    assert lookup.observed_instance_id == "other"


@pytest.mark.asyncio
async def test_absent_container_is_missing(tmp_path):
    core = _core(tmp_path, _Client([]))

    lookup = await core._lookup_browser_container("p1", "inst1")

    assert lookup.outcome == "missing"


@pytest.mark.asyncio
async def test_docker_failure_stays_unresolved(tmp_path):
    core = _core(tmp_path, _Client(error=RuntimeError("docker down")))

    lookup = await core._lookup_browser_container("p1", "inst1")

    assert lookup.outcome == "unavailable"
