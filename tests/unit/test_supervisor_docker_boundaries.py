"""Docker scan and helper-container boundaries (t022 A9/A10)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator
from docker.errors import DockerException

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def _adapter(tmp_path, client) -> DockerAdapter:
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


def _container(name: str, labels: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"id-{name}", name=name, status="running", labels=labels, attrs={"Mounts": []}
    )


def _labels(**overrides) -> dict:
    labels = {
        "com.cbrowser.role": "browser",
        "com.cbrowser.profile-id": "profile_a",
        "com.cbrowser.instance-id": "instance_a",
        "com.cbrowser.config-version": "3",
    }
    labels.update(overrides)
    return labels


def test_scan_isolates_containers_with_bad_config_version(tmp_path) -> None:
    """A10: missing/malformed config-version or identity labels reject only
    that resource; valid resources in the same scan are still returned."""
    valid = _container("valid", _labels())
    missing_version = _container(
        "missing",
        {k: v for k, v in _labels().items() if "config-version" not in k},
    )
    malformed = _container("bad", _labels(**{"com.cbrowser.config-version": "abc"}))
    no_instance = _container(
        "ghost",
        {k: v for k, v in _labels().items() if "instance-id" not in k},
    )
    valid_stream = _container(
        "stream", _labels(**{"com.cbrowser.role": "stream"})
    )
    client = SimpleNamespace(
        containers=SimpleNamespace(
            list=lambda **_kw: [valid, missing_version, malformed, no_instance, valid_stream]
        )
    )
    adapter = _adapter(tmp_path, client)
    result = adapter.scan_active_containers()
    assert [entry["name"] for entry in result] == ["valid", "stream"]
    assert result[0]["config_version"] == "3"


class _FakeHelper:
    def __init__(self, status_code: int) -> None:
        self._status_code = status_code
        self.removed = False

    def wait(self, timeout=None) -> dict:
        return {"StatusCode": self._status_code}

    def remove(self, force: bool = False) -> None:
        self.removed = True


def test_policy_verification_helper_has_deterministic_managed_name(tmp_path) -> None:
    """A9/f006: verify/fail-closed helpers must carry the reaper name too.
    An auto-generated Docker name would make the startup orphan reaper
    raise a false ownership mismatch after a mid-verification SIGKILL.
    """
    import re

    helper = _FakeHelper(0)
    calls: dict = {}

    def run(image, **kwargs):
        calls.update(kwargs)
        return helper

    client = SimpleNamespace(containers=SimpleNamespace(run=run))
    adapter = _adapter(tmp_path, client)
    target = SimpleNamespace(
        id="target-id", labels={"com.cbrowser.instance-id": "inst_a"}
    )
    assert (
        adapter.verify_container_policy(
            target,
            {
                "role": "stream",
                "udp_mux_port": 30005,
                "allowed_tcp": [],
                "allowed_udp": [],
            },
        )
        is True
    )
    assert re.fullmatch(
        rf"{re.escape(adapter.resource_prefix)}-policy-[0-9a-f]{{12}}",
        calls["name"],
    )
    assert helper.removed is True


def test_x11_helper_is_least_privilege_and_cleaned_up(tmp_path) -> None:
    """A9: the X11 permission helper drops all capabilities except the one
    chmod needs, runs on a read-only rootfs with no-new-privileges, carries
    managed labels, and is removed after a successful run."""
    helper = _FakeHelper(0)
    calls: dict = {}

    def run(image, **kwargs):
        calls["image"] = image
        calls.update(kwargs)
        return helper

    client = SimpleNamespace(containers=SimpleNamespace(run=run))
    adapter = _adapter(tmp_path, client)
    adapter.setup_x11_permissions(tmp_path / "x11")
    assert calls["cap_drop"] == ["ALL"]
    assert calls["cap_add"] == ["FOWNER"]
    assert calls["read_only"] is True
    assert "no-new-privileges:true" in calls["security_opt"]
    assert calls["labels"]["com.cbrowser.role"] == "x11-permissions"
    assert calls["labels"]["com.cbrowser.managed-by"] == "supervisor"
    assert helper.removed is True


def test_x11_helper_nonzero_exit_is_an_explicit_failure(tmp_path) -> None:
    """A9: a failed permission fix reports failure and still cleans up."""
    helper = _FakeHelper(1)
    client = SimpleNamespace(
        containers=SimpleNamespace(run=lambda *_a, **_kw: helper)
    )
    adapter = _adapter(tmp_path, client)
    with pytest.raises(DockerSandboxError):
        adapter.setup_x11_permissions(tmp_path / "x11")
    assert helper.removed is True


def test_x11_helper_launch_failure_is_an_explicit_error(tmp_path) -> None:
    """A9: a helper that cannot even start surfaces a sandbox error."""

    def run(*_a, **_kw):
        raise DockerException("daemon down")

    client = SimpleNamespace(containers=SimpleNamespace(run=run))
    adapter = _adapter(tmp_path, client)
    with pytest.raises(DockerSandboxError):
        adapter.setup_x11_permissions(tmp_path / "x11")


def test_x11_helper_wait_failure_still_cleans_up(tmp_path) -> None:
    """A9: if waiting on the helper fails (daemon error/cancellation of the
    wait), the error surfaces explicitly and the helper is still removed."""

    class _WaitFailingHelper(_FakeHelper):
        def wait(self, timeout=None) -> dict:
            raise DockerException("wait interrupted")

    helper = _WaitFailingHelper(0)
    client = SimpleNamespace(
        containers=SimpleNamespace(run=lambda *_a, **_kw: helper)
    )
    adapter = _adapter(tmp_path, client)
    with pytest.raises(DockerSandboxError):
        adapter.setup_x11_permissions(tmp_path / "x11")
    assert helper.removed is True


def test_x11_helper_remove_failure_never_masks_the_outcome(tmp_path) -> None:
    """A9/f007: a failing helper.remove() is logged, not raised — it must
    not turn a successful permission fix into a reported failure."""

    class _RemoveFailingHelper(_FakeHelper):
        def remove(self, force: bool = False) -> None:
            raise DockerException("daemon gone")

    helper = _RemoveFailingHelper(0)
    calls: dict = {}

    def run(image, **kwargs):
        calls.update(kwargs)
        return helper

    client = SimpleNamespace(containers=SimpleNamespace(run=run))
    adapter = _adapter(tmp_path, client)
    adapter.setup_x11_permissions(tmp_path / "x11")  # must not raise
    # f006: the helper carries the deterministic managed name the startup
    # orphan reaper recognizes.
    assert calls["name"].startswith(f"{adapter.resource_prefix}-x11-")


def test_x11_orphan_helper_is_reaped_at_startup(tmp_path) -> None:
    """A9/f006: an exited x11-permissions helper with the deterministic
    name is collected by the same orphan reaper as the other helpers."""
    client = SimpleNamespace(containers=SimpleNamespace(list=lambda **_kw: []))
    adapter = _adapter(tmp_path, client)
    prefix = adapter.resource_prefix
    orphan = SimpleNamespace(
        name=f"{prefix}-x11-{'a' * 12}",
        labels={
            "com.cbrowser.prefix": prefix,
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": "x11-permissions",
        },
        removed=False,
    )

    def remove(force: bool = False) -> None:
        orphan.removed = True

    orphan.remove = remove
    adapter.client = SimpleNamespace(
        containers=SimpleNamespace(list=lambda **_kw: [orphan])
    )
    adapter._cleanup_orphan_helpers()
    assert orphan.removed is True
