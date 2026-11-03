"""Shared DockerAdapter contract doubles for supervisor tests (t024 AC-014/A43).

One canonical fake for the Docker client/adapter surface the Supervisor
consumes, so per-file minimal fakes cannot drift from the contract
independently.  The naming scheme mirrors the production DockerAdapter
(``{resource_prefix}-browser-{profile_id}`` with the production default
prefix), and tests/unit/test_docker_doubles_contract.py holds the fake and
the real adapter to the same observable contract.  Specialized suites
(e.g. the normal-exit replay, which models container state machines) may
subclass or compose these.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from docker.errors import NotFound


class FakeContainer:
    """Minimal container record: labels + status, as the adapter reads."""

    def __init__(self, instance_id: str, status: str = "running") -> None:
        self.labels = {"com.cbrowser.instance-id": instance_id}
        self.status = status


class FakeContainers:
    """containers collection: get() raises docker NotFound when absent."""

    def __init__(self) -> None:
        self.container: FakeContainer | None = None

    def get(self, _name: str) -> FakeContainer:
        if self.container is None:
            raise NotFound("no browser container")
        return self.container

    def list(self, **_kwargs) -> list[FakeContainer]:
        return [self.container] if self.container is not None else []


class FakeDockerClient:
    """The client surface: .containers plus a SimpleNamespace-free shape."""

    def __init__(self) -> None:
        self.containers = FakeContainers()


def fake_docker_client() -> SimpleNamespace:
    """Namespace wrapper matching how SupervisorCore receives the client."""
    return SimpleNamespace(containers=FakeContainers())


class FakeDockerAdapter:
    """Adapter-facing double with the production naming contract.

    Mirrors DockerAdapter's observable surface that SupervisorCore uses in
    the observation/recovery suites: validator, containers, client,
    container naming, and an empty active-container scan.
    """

    def __init__(
        self, data_root: Path, *, resource_prefix: str = "cbrowser-t005"
    ) -> None:
        from cbrowser.supervisor.path_validator import PathValidator

        self.validator = PathValidator(data_root)
        self.resource_prefix = resource_prefix
        self.containers = FakeContainers()
        self.client = fake_docker_client()
        # Keep the client's containers the same object as the adapter's so
        # tests can stage containers through either handle.
        self.client.containers = self.containers

    def get_browser_container_name(self, profile_id: str) -> str:
        return f"{self.resource_prefix}-browser-{profile_id}"

    def get_stream_container_name(self, profile_id: str) -> str:
        return f"{self.resource_prefix}-stream-{profile_id}"

    def scan_active_containers(self) -> list[dict]:
        return []
