"""Contract comparison: shared Docker doubles vs the real DockerAdapter.

t024 AC-014/A43 (review f007): the shared test doubles must provably match
the production adapter's observable contract on the surface the suites
consume — container naming and the containers collection semantics — so a
drift on either side turns this test red instead of silently diverging.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docker.errors import NotFound

from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator
from docker_doubles import FakeContainer, FakeDockerAdapter, FakeDockerClient

_SHA = "sha256:" + "a" * 64


def _real_adapter(tmp_path: Path) -> DockerAdapter:
    # The production validator requires the cache root to exist (in
    # deployment it is pre-created); mirror that precondition.
    (tmp_path / "engine-cache" / "geoip").mkdir(parents=True, exist_ok=True)
    return DockerAdapter(
        PathValidator(tmp_path),
        tmp_path / "engine-cache",
        docker_client=FakeDockerClient(),
        browser_image=_SHA,
        stream_image=_SHA,
    )


def test_container_naming_matches_production(tmp_path: Path) -> None:
    real = _real_adapter(tmp_path)
    fake = FakeDockerAdapter(tmp_path)
    for profile_id in ("p1", "profile-xyz"):
        assert fake.get_browser_container_name(profile_id) == (
            real.get_browser_container_name(profile_id)
        )
        assert fake.get_stream_container_name(profile_id) == (
            real.get_stream_container_name(profile_id)
        )


def _sdk_containers():
    """The real docker SDK containers collection over a stubbed API layer.

    Only the two API calls behind get/list are stubbed, with the SDK's own
    error semantics (inspect on a missing container raises NotFound), so
    the behavior matrix below runs the SDK's actual collection code.
    """
    from types import SimpleNamespace

    from docker.models.containers import ContainerCollection

    def _inspect(_name):
        raise NotFound("No such container")

    api = SimpleNamespace(
        inspect_container=_inspect,
        containers=lambda **_kw: [],
    )
    return ContainerCollection(client=SimpleNamespace(api=api))


def test_containers_collection_semantics_match_docker_sdk(tmp_path: Path) -> None:
    fake = FakeDockerAdapter(tmp_path)
    sdk = _sdk_containers()
    # Same behavior matrix on both sides (t024 review f011: the comparison
    # must exercise the SDK collection, not only the double).
    for containers in (fake.containers, sdk):
        with pytest.raises(NotFound):
            containers.get("missing")
        assert containers.list() == []
    # Present container on the double: get returns it, list surfaces it.
    staged = FakeContainer("inst-1", "running")
    fake.containers.container = staged
    assert fake.containers.get("any") is staged
    assert fake.containers.list() == [staged]
    assert staged.labels == {"com.cbrowser.instance-id": "inst-1"}
    assert staged.status == "running"


def test_scan_active_containers_empty_by_default(tmp_path: Path) -> None:
    fake = FakeDockerAdapter(tmp_path)
    assert fake.scan_active_containers() == []
