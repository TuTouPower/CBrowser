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
    """Minimal container record: runtime config + status, as readers use.

    The per-launch runtime instance id lives in the container's runtime
    configuration (the Stream environment channel), mirroring
    production; ``com.cbrowser.instance-id`` is a label only for the
    deployment instance id, so labels start empty.
    """

    def __init__(self, instance_id: str, status: str = "running") -> None:
        self.labels: dict[str, str] = {}
        self.attrs = {
            "Config": {
                "Env": [f"CBROWSER_RUNTIME_INSTANCE_ID={instance_id}"],
            }
        }
        self.status = status


class FakeContainers:
    """containers collection: get() raises docker NotFound when absent."""

    def __init__(self) -> None:
        self._containers: dict[str, FakeContainer] = {}

    def register(self, name: str, container: FakeContainer) -> None:
        self._containers[name] = container

    def get(self, name: str) -> FakeContainer:
        if name not in self._containers:
            raise NotFound(f"no such container: {name}")
        return self._containers[name]

    def list(self, **_kwargs) -> list[FakeContainer]:
        return list(self._containers.values())


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
        # Mirrors an unconfigured DockerAdapter: no deployment identity.
        self.deployment_instance_id: str | None = None
        self.containers = FakeContainers()
        self.client = fake_docker_client()
        # Keep the client's containers the same object as the adapter's so
        # tests can stage containers through either handle.
        self.client.containers = self.containers
        self.profile_numbers: dict[str, int] = {}

    def remember_profile_number(self, profile_id: str, number: int) -> None:
        self.profile_numbers[profile_id] = number

    def _profile_number(self, profile_id: str) -> int:
        try:
            return self.profile_numbers[profile_id]
        except KeyError:
            raise RuntimeError(
                "FakeDockerAdapter requires remember_profile_number"
            ) from None

    def get_browser_container_name(self, profile_id: str) -> str:
        return f"{self.resource_prefix}-{self._profile_number(profile_id):04d}-browser"

    def get_stream_container_name(self, profile_id: str) -> str:
        return f"{self.resource_prefix}-{self._profile_number(profile_id):04d}-stream"

    def scan_active_containers(self) -> list[dict]:
        return []
