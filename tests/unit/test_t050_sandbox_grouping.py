"""t050: Profile sandboxes share one pseudo compose project.

Docker Desktop groups containers by ``com.docker.compose.project``. The
Supervisor-created Browser/Stream containers therefore carry an explicit
``<prefix>-profiles`` project plus their service role, so every running
Profile appears under one group instead of as unrelated containers.
"""

from __future__ import annotations

from cbrowser.supervisor.container_spec import browser_labels, stream_labels

PREFIX = "cbrowser"


def test_browser_labels_carry_sandbox_group():
    labels = browser_labels(PREFIX, "profile-1", "inst-1", 3, 1)
    assert labels["com.docker.compose.project"] == "cbrowser-profiles"
    assert labels["com.docker.compose.service"] == "browser"
    assert labels["com.cbrowser.profile-number"] == "0001"
    # Existing ownership labels remain the source of truth.
    assert labels["com.cbrowser.prefix"] == PREFIX
    assert labels["com.cbrowser.role"] == "browser"
    assert labels["com.cbrowser.profile-id"] == "profile-1"
    assert labels["com.cbrowser.instance-id"] == "inst-1"


def test_stream_labels_carry_sandbox_group():
    labels = stream_labels(PREFIX, "profile-1", "inst-1", 3, 1)
    assert labels["com.docker.compose.project"] == "cbrowser-profiles"
    assert labels["com.docker.compose.service"] == "stream"
    assert labels["com.cbrowser.profile-number"] == "0001"
    assert labels["com.cbrowser.prefix"] == PREFIX
    assert labels["com.cbrowser.role"] == "stream"


def test_group_follows_deployment_prefix():
    labels = browser_labels("inst-b", "profile-1", "inst-1", 1, 7)
    assert labels["com.docker.compose.project"] == "inst-b-profiles"
    assert labels["com.cbrowser.profile-number"] == "0007"


def test_sandbox_container_names_use_zero_padded_number():
    from docker_doubles import FakeDockerAdapter

    fake = FakeDockerAdapter(__import__("pathlib").Path("/tmp"))
    fake.remember_profile_number("profile-1", 7)
    assert fake.get_browser_container_name("profile-1") == "cbrowser-t005-0007-browser"
    assert fake.get_stream_container_name("profile-1") == "cbrowser-t005-0007-stream"


def test_start_request_requires_positive_profile_number():
    from cbrowser.supervisor.protocol import StartProfileRequest
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        StartProfileRequest(profile_id="p1", config_version=1)
    with pytest.raises(ValidationError):
        StartProfileRequest(profile_id="p1", profile_number=0, config_version=1)
    request = StartProfileRequest(
        profile_id="p1", profile_number=3, config_version=1
    )
    assert request.profile_number == 3


def test_runtime_and_profile_responses_expose_positive_number():
    from cbrowser.domain.models import ProfileResponse, ProfileRuntimeResponse
    import pytest

    runtime = ProfileRuntimeResponse(
        profile_id="p1",
        display_number=4,
        desired_state="stopped",
        observed_state="stopped",
        runtime_instance_id=None,
        config_version=1,
        failure_count=0,
        restart_blocked=False,
        last_exit_event_id=None,
        updated_at="2026-01-01T00:00:00Z",
    )
    assert isinstance(runtime.display_number, int)
    assert runtime.display_number > 0
    with pytest.raises(Exception):
        ProfileRuntimeResponse.model_validate({**runtime.model_dump(), "display_number": None})


def test_profile_number_label_parser_rejects_garbage():
    from cbrowser.supervisor.docker_adapter import _parse_profile_number

    assert _parse_profile_number("0001") == 1
    assert _parse_profile_number(3) == 3
    assert _parse_profile_number("0") is None
    assert _parse_profile_number("abc") is None
    assert _parse_profile_number(None) is None
    assert _parse_profile_number(True) is None


def test_scan_recovers_number_from_labels_and_rejects_missing(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from cbrowser.supervisor.docker_adapter import DockerAdapter
    from cbrowser.supervisor.path_validator import PathValidator

    (tmp_path / "data" / "engine" / "geoip").mkdir(parents=True)
    good = SimpleNamespace(
        id="c1",
        name="legacy-container-name",
        status="running",
        labels={
            "com.cbrowser.prefix": "cbrowser",
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": "browser",
            "com.cbrowser.profile-id": "p1",
            "com.cbrowser.instance-id": "i1",
            "com.cbrowser.config-version": "1",
            "com.cbrowser.profile-number": "0003",
        },
    )
    bad = SimpleNamespace(
        id="c2",
        name="cbrowser-legacy-browser",
        status="running",
        labels={
            "com.cbrowser.prefix": "cbrowser",
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": "browser",
            "com.cbrowser.profile-id": "p2",
            "com.cbrowser.instance-id": "i2",
            "com.cbrowser.config-version": "1",
        },
    )
    client = MagicMock()
    client.containers.list.return_value = [good, bad]
    adapter = DockerAdapter(
        path_validator=PathValidator(tmp_path / "data"),
        engine_cache_dir=tmp_path / "data" / "engine",
        docker_client=client,
        browser_image="sha256:" + "a" * 64,
        stream_image="sha256:" + "b" * 64,
        resource_prefix="cbrowser",
    )
    adapter._runtime_policy_ready = MagicMock(return_value=True)

    scanned = adapter.scan_active_containers()

    assert [item["profile_id"] for item in scanned] == ["p1"]
    assert adapter.get_browser_container_name("p1") == "cbrowser-0003-browser"
    import pytest

    with pytest.raises(Exception):
        adapter.get_browser_container_name("p2")


def test_cleanup_container_by_name_enforces_numbered_identity(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
    from cbrowser.supervisor.path_validator import PathValidator
    import pytest

    (tmp_path / "data" / "engine" / "geoip").mkdir(parents=True)
    container = SimpleNamespace(
        name="cbrowser-0005-browser",
        labels={
            "com.cbrowser.prefix": "cbrowser",
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": "browser",
            "com.cbrowser.profile-id": "p1",
            "com.cbrowser.profile-number": "0005",
        },
        remove=MagicMock(),
    )
    client = MagicMock()
    client.containers.get.return_value = container
    adapter = DockerAdapter(
        path_validator=PathValidator(tmp_path / "data"),
        engine_cache_dir=tmp_path / "data" / "engine",
        docker_client=client,
        browser_image="sha256:" + "a" * 64,
        stream_image="sha256:" + "b" * 64,
        resource_prefix="cbrowser",
    )
    adapter.cleanup_container_by_name("cbrowser-0005-browser")
    container.remove.assert_called_once_with(force=True)

    with pytest.raises(DockerSandboxError):
        adapter.cleanup_container_by_name("cbrowser-0006-browser")


def test_scan_keeps_number_and_name_across_restarts(tmp_path):
    """A restarted adapter recovers the number from container labels, so
    the same Profile keeps its name without any in-memory carry-over."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from cbrowser.supervisor.docker_adapter import DockerAdapter
    from cbrowser.supervisor.path_validator import PathValidator

    (tmp_path / "data" / "engine" / "geoip").mkdir(parents=True)
    labels = {
        "com.cbrowser.prefix": "cbrowser",
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "browser",
        "com.cbrowser.profile-id": "p1",
        "com.cbrowser.instance-id": "i1",
        "com.cbrowser.config-version": "1",
        "com.cbrowser.profile-number": "0005",
    }
    container = SimpleNamespace(
        id="c1", name="legacy-name", status="running", labels=labels
    )

    def adapter():
        client = MagicMock()
        client.containers.list.return_value = [container]
        instance = DockerAdapter(
            path_validator=PathValidator(tmp_path / "data"),
            engine_cache_dir=tmp_path / "data" / "engine",
            docker_client=client,
            browser_image="sha256:" + "a" * 64,
            stream_image="sha256:" + "b" * 64,
            resource_prefix="cbrowser",
        )
        instance._runtime_policy_ready = MagicMock(return_value=True)
        return instance

    first = adapter()
    first.scan_active_containers()
    second = adapter()
    second.scan_active_containers()

    assert first.get_browser_container_name("p1") == "cbrowser-0005-browser"
    assert second.get_browser_container_name("p1") == "cbrowser-0005-browser"
    assert second.get_stream_container_name("p1") == "cbrowser-0005-stream"


def test_fake_adapter_fails_closed_without_number(tmp_path):
    from docker_doubles import FakeDockerAdapter
    import pytest

    with pytest.raises(RuntimeError):
        FakeDockerAdapter(tmp_path).get_browser_container_name("p1")
