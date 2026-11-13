"""Real-container X11 permission helper E2E (t028 AC-004).

The Supervisor fixes the X11 socket directory with a one-shot,
least-privilege helper container (production
``DockerAdapter.setup_x11_permissions``).  Unit tests cover the launch
contract against a fake client; this entry runs the same production
method against a real Docker daemon and asserts the observable
outcome: the directory mode becomes 0750 and no helper container is
left behind.  Target-environment execution is t032's.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import docker
import pytest
from e2e_env import require_e2e_env

from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator


def _leftover_helpers(client: docker.DockerClient, prefix: str) -> list:
    return client.containers.list(
        all=True,
        filters={
            "label": [
                f"com.cbrowser.prefix={prefix}",
                "com.cbrowser.role=x11-permissions",
            ]
        },
    )


def test_x11_helper_converges_linux_mount_permissions_after_drift(
    tmp_path: Path,
) -> None:
    image = require_e2e_env("CBROWSER_RUNTIME_TEST_IMAGE")[
        "CBROWSER_RUNTIME_TEST_IMAGE"
    ]
    assert image.startswith("sha256:"), (
        f"CBROWSER_RUNTIME_TEST_IMAGE must be sha256 immutable digest, got {image}"
    )
    client = docker.from_env()
    try:
        client.images.get(image)
        cache = tmp_path / "engine_cache"
        (cache / "geoip").mkdir(parents=True)
        prefix = "t028-x11-" + uuid.uuid4().hex[:10]
        adapter = DockerAdapter(
            PathValidator(tmp_path),
            cache,
            docker_client=client,
            browser_image=image,
            stream_image=image,
            resource_prefix=prefix,
        )
        x11_dir = tmp_path / "x11"
        x11_dir.mkdir()

        def mount_command(entrypoint, command):
            return client.containers.run(
                image, entrypoint=entrypoint, command=command,
                volumes={str(x11_dir): {"bind": "/x11", "mode": "rw"}},
                user="0:0", read_only=True, cap_drop=["ALL"], cap_add=["FOWNER"],
                security_opt=["no-new-privileges:true"], remove=True,
            )

        try:
            for drift in ("0700", "0711"):
                mount_command("chmod", [drift, "/x11"])
                assert int(mount_command("stat", ["-c", "%a", "/x11"]).strip(), 8) == int(drift, 8)
                adapter.setup_x11_permissions(x11_dir)
                assert int(mount_command("stat", ["-c", "%a", "/x11"]).strip(), 8) == 0o750
                assert _leftover_helpers(client, prefix) == []
        finally:
            for container in _leftover_helpers(client, prefix):
                container.remove(force=True)
    finally:
        client.close()


def test_x11_helper_failure_is_explicit_with_real_daemon(
    tmp_path: Path,
) -> None:
    """A helper image that does not exist locally fails explicitly."""
    require_e2e_env("CBROWSER_RUNTIME_TEST_IMAGE")
    client = docker.from_env()
    try:
        cache = tmp_path / "engine_cache"
        (cache / "geoip").mkdir(parents=True)
        prefix = "t028-x11-missing-" + uuid.uuid4().hex[:10]
        missing_image = "sha256:" + "0" * 64
        adapter = DockerAdapter(
            PathValidator(tmp_path),
            cache,
            docker_client=client,
            browser_image=missing_image,
            stream_image=missing_image,
            resource_prefix=prefix,
        )
        x11_dir = tmp_path / "x11"
        x11_dir.mkdir()
        with pytest.raises(Exception) as caught:
            adapter.setup_x11_permissions(x11_dir)
        assert type(caught.value).__name__ == "DockerSandboxError"
        assert _leftover_helpers(client, prefix) == []
    finally:
        client.close()

pytestmark = pytest.mark.e2e_images('CBROWSER_RUNTIME_TEST_IMAGE')
