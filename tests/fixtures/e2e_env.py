"""Single source of truth for E2E environment prerequisites."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, Mapping

import pytest

REQUIRED_E2E_ENV = {
    "CBROWSER_RUNTIME_TEST_IMAGE": "Browser Runtime image sha256",
    "CBROWSER_STREAM_TEST_IMAGE": "Stream Runtime image sha256",
    "CBROWSER_GATEWAY_IMAGE": "Gateway image sha256",
    "CBROWSER_SUPERVISOR_TEST_IMAGE": "Supervisor image sha256",
    "CBROWSER_API_TEST_IMAGE": "API image sha256",
    "CBROWSER_CADDY_TEST_IMAGE": "Caddy image sha256",
    "CBROWSER_RUNTIME_ENGINE_CACHE": "initialized Linux engine cache",
    "CBROWSER_RUNTIME_GEOIP_CACHE": "GeoIP cache",
    "CBROWSER_INVALID_POLICY_TEST_IMAGE": "invalid-policy test image",
}


def require_e2e_env(*names: str, paths: tuple[str, ...] = ()) -> dict[str, str]:
    """Return required env values; fail in required mode, skip otherwise."""
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        message = "Missing required E2E environment variables: " + ", ".join(missing)
        if os.environ.get("CBROWSER_E2E_REQUIRED") == "1":
            pytest.fail(message, pytrace=False)
        pytest.skip(message)
    values = {name: os.environ[name] for name in names}
    for name in paths:
        if not Path(values[name]).is_dir():
            pytest.fail(
                f"E2E path is not a directory: {values[name]}", pytrace=False
            )
    return values


IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def is_image_env_var(name: str) -> bool:
    """True for REQUIRED_E2E_ENV entries that must hold an image ID."""
    return name in REQUIRED_E2E_ENV and name.endswith("_IMAGE")


def _docker_image_exists(image_id: str) -> bool:
    import docker

    client = docker.from_env()
    try:
        client.images.get(image_id)
        return True
    except docker.errors.ImageNotFound:
        return False
    finally:
        client.close()


def image_identity_problems(
    environ: Mapping[str, str] | None = None,
    image_exists: Callable[[str], bool] | None = None,
) -> list[str]:
    """Fail-closed identity checks for every E2E image variable that is set.

    A set image variable must hold an immutable ``sha256:`` ID that
    resolves to a locally present image; a tag, a short digest, a missing
    local image, or an unresolvable daemon lookup are all explicit
    problems.  Unset variables are the presence gate's concern, not this
    function's.  ``image_exists`` is injectable for unit tests.
    """
    env = os.environ if environ is None else environ
    exists = _docker_image_exists if image_exists is None else image_exists
    problems: list[str] = []
    for name in REQUIRED_E2E_ENV:
        if not is_image_env_var(name):
            continue
        value = env.get(name)
        if not value:
            continue
        if not IMAGE_ID_RE.match(value):
            problems.append(
                f"{name}: not an immutable sha256 image ID: {value!r}"
            )
            continue
        try:
            resolved = exists(value)
        except Exception as exc:  # daemon unreachable, auth failure, ...
            problems.append(
                f"{name}: cannot resolve image {value}: {type(exc).__name__}"
            )
            continue
        if not resolved:
            problems.append(f"{name}: image not present locally: {value}")
    return problems


def collect_image_identity_evidence(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Map each set E2E image variable to the image ID actually in use.

    Evidence records must name the real IDs a run executed against, so a
    plain collection can never be mistaken for an executed run.
    """
    env = os.environ if environ is None else environ
    return {
        name: env[name]
        for name in REQUIRED_E2E_ENV
        if is_image_env_var(name) and env.get(name)
    }


def free_udp_port_span(count: int = 2, *, start: int = 30000, end: int = 30990) -> int:
    """Return a base port with ``count`` consecutive free loopback UDP ports."""
    import socket

    for base in range(start, end - count + 1):
        sockets = []
        try:
            for offset in range(count):
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(("127.0.0.1", base + offset))
                sockets.append(sock)
            return base
        except OSError:
            continue
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError("No free consecutive UDP port range found")
