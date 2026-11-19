"""Real-container X11 permission helper E2E (t028 AC-004).

The Supervisor fixes the X11 socket directory with a one-shot,
least-privilege helper container (production
``DockerAdapter.setup_x11_permissions``).  Unit tests cover the launch
contract against a fake client; this entry runs the same production
method inside the Supervisor image against a real Docker daemon and named
runtime volume subpath, asserting the observable outcome: the directory
mode converges to 0750 and no helper container is left behind.
"""

from __future__ import annotations

import uuid

import docker
from docker.types import Mount
import pytest

from e2e_env import require_e2e_env
from e2e_volumes import init_prefix_volumes, remove_prefix_volumes, run_volume_json
from cbrowser.supervisor.gate_identity import gate_labels

pytestmark = [
    pytest.mark.e2e_images(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
    )
]

_X11_DRIVER = """
import json
import os
from pathlib import Path

import docker
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator

client = docker.from_env()
try:
    adapter = DockerAdapter(
        PathValidator("/data"),
        Path("/data/engine-cache"),
        docker_client=client,
        browser_image=os.environ["CB_TEST_HELPER_IMAGE"],
        stream_image=os.environ["CB_TEST_HELPER_IMAGE"],
        resource_prefix=os.environ["CB_TEST_PREFIX"],
    )
    target = Path(os.environ["CB_TEST_X11_DIR"])
    target.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CB_EXPECT_FAIL") == "1":
        try:
            adapter.setup_x11_permissions(target)
        except DockerSandboxError as exc:
            print("CBROWSER_E2E_RESULT=" + json.dumps({"error_type": type(exc).__name__}))
        else:
            raise AssertionError("Expected DockerSandboxError")
    else:
        adapter.setup_x11_permissions(target)
        print("CBROWSER_E2E_RESULT=" + json.dumps({"ok": True}))
finally:
    client.close()
"""


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


def test_x11_helper_converges_linux_mount_permissions_after_drift() -> None:
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
    )
    image = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    supervisor_image = env["CBROWSER_SUPERVISOR_TEST_IMAGE"]
    assert image.startswith("sha256:"), (
        f"CBROWSER_RUNTIME_TEST_IMAGE must be sha256 immutable digest, got {image}"
    )
    client = docker.from_env()
    prefix = "t028-x11-" + uuid.uuid4().hex[:10]
    subpath = "x11_drift"
    try:
        client.images.get(image)
        client.images.get(supervisor_image)
        init_prefix_volumes(
            client,
            prefix,
            supervisor_image,
            roles=("data", "runtime", "fonts"),
        )
        run_volume_json(
            client,
            prefix,
            supervisor_image,
            (
                "import json, os; from pathlib import Path; "
                "d = Path(f'/data/runtime/{os.environ[\"CB_SUBPATH\"]}'); "
                "d.mkdir(parents=True, exist_ok=True); "
                "print('CBROWSER_E2E_RESULT=' + json.dumps({'ok': True}))"
            ),
            roles=("runtime",),
            env={"CB_SUBPATH": subpath},
        )

        def mount_command(entrypoint: str, command: list[str]) -> str:
            out = client.containers.run(
                image,
                entrypoint=entrypoint,
                command=command,
                mounts=[
                    Mount(
                        target="/x11",
                        source=f"{prefix}-runtime",
                        type="volume",
                        subpath=subpath,
                    )
                ],
                user="0:0",
                read_only=True,
                cap_drop=["ALL"],
                cap_add=["FOWNER", "DAC_OVERRIDE"],
                security_opt=["no-new-privileges:true"],
                labels=gate_labels(
                    {
                        "com.cbrowser.prefix": prefix,
                        "com.cbrowser.managed-by": "supervisor",
                        "com.cbrowser.role": "e2e-x11-probe",
                    }
                ),
                remove=True,
            )
            return out.decode("utf-8", errors="replace")

        try:
            for drift in ("0700", "0711"):
                mount_command("chmod", [drift, "/x11"])
                assert int(mount_command("stat", ["-c", "%a", "/x11"]).strip(), 8) == int(
                    drift, 8
                )
                res = run_volume_json(
                    client,
                    prefix,
                    supervisor_image,
                    _X11_DRIVER,
                    roles=("data", "runtime", "fonts"),
                    mount_docker_sock=True,
                    env={
                        "CB_TEST_PREFIX": prefix,
                        "CB_TEST_HELPER_IMAGE": image,
                        "CB_TEST_X11_DIR": f"/data/runtime/{subpath}",
                    },
                )
                assert res == {"ok": True}
                assert (
                    int(mount_command("stat", ["-c", "%a", "/x11"]).strip(), 8)
                    == 0o750
                )
                assert _leftover_helpers(client, prefix) == []
        finally:
            for container in client.containers.list(
                all=True, filters={"label": f"com.cbrowser.prefix={prefix}"}
            ):
                container.remove(force=True)
    finally:
        remove_prefix_volumes(client, prefix)
        client.close()


def test_x11_helper_failure_is_explicit_with_real_daemon() -> None:
    """A helper image that does not exist locally fails explicitly."""
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
    )
    supervisor_image = env["CBROWSER_SUPERVISOR_TEST_IMAGE"]
    client = docker.from_env()
    prefix = "t028-x11-missing-" + uuid.uuid4().hex[:10]
    missing_image = "sha256:" + "0" * 64
    try:
        client.images.get(supervisor_image)
        init_prefix_volumes(
            client,
            prefix,
            supervisor_image,
            roles=("data", "runtime", "fonts"),
        )
        res = run_volume_json(
            client,
            prefix,
            supervisor_image,
            _X11_DRIVER,
            roles=("data", "runtime", "fonts"),
            mount_docker_sock=True,
            env={
                "CB_TEST_PREFIX": prefix,
                "CB_TEST_HELPER_IMAGE": missing_image,
                "CB_TEST_X11_DIR": "/data/runtime/x11_missing",
                "CB_EXPECT_FAIL": "1",
            },
        )
        assert res["error_type"] == "DockerSandboxError"
        assert _leftover_helpers(client, prefix) == []
    finally:
        for container in _leftover_helpers(client, prefix):
            container.remove(force=True)
        remove_prefix_volumes(client, prefix)
        client.close()
