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
    "CBROWSER_NETWORK_POLICY_IMAGE": "network-policy image sha256",
}


def _required_mode() -> bool:
    return os.environ.get("CBROWSER_E2E_REQUIRED") == "1"


def require_e2e_available(condition: bool, message: str) -> None:
    """Single fail-closed gate for every E2E prerequisite (t044 AC-005).

    A missing prerequisite aborts a required-mode run and skips an optional
    one; a bare ``pytest.skip`` would let required-mode runs pass green
    without ever exercising the topology.  ``require_e2e_env`` and the
    suites both route their checks through here so the two modes can never
    diverge.
    """
    if condition:
        return
    if _required_mode():
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def _docker_daemon_ok() -> bool:
    """True when ``docker.from_env().ping()`` reaches the daemon."""
    import docker

    client = docker.from_env()
    try:
        client.ping()
        return True
    finally:
        client.close()


def complete_font_set_dir(platform: str, root: Path | str) -> Path | None:
    """Return the newest ``ok=True`` imported font-set directory for a platform.

    Only complete, intact sets published by ``scripts/import_font_set.py``
    qualify; the production manifest verifier is the single source of truth
    for what counts as a usable platform font set.
    """
    from cbrowser.font_sets import list_font_sets

    base = Path(root)
    candidates = [
        item
        for item in list_font_sets(base)
        if item["platform"] == platform and item["integrity"]["ok"]
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (str(item.get("created_at") or ""), item["set_id"])
    )
    target = base / platform / candidates[-1]["set_id"]
    if not target.is_dir() or not (target / "manifest.json").is_file():
        return None
    return target


def require_e2e_env(
    *names: str,
    paths: tuple[str, ...] = (),
    docker: bool = False,
    fonts_platform: str | None = None,
) -> dict[str, str]:
    """Return required env values; fail in required mode, skip otherwise.

    ``names`` are env variables that must be set.  ``paths`` are env
    variables whose values must be existing directories.  ``docker`` pings
    the daemon.  ``fonts_platform`` resolves an intact imported font set for
    that platform and exposes its directory under the ``_fonts_dir`` key.
    Every failure/skip message enumerates the concrete missing items.
    """
    missing = [name for name in names if not os.environ.get(name)]
    require_e2e_available(
        not missing,
        "Missing required E2E environment variables: " + ", ".join(missing),
    )
    values = {name: os.environ[name] for name in names}

    path_problems = []
    for name in paths:
        value = values.get(name, os.environ.get(name))
        if not value or not Path(value).is_dir():
            path_problems.append(
                f"{name}={value!r} is not an existing directory"
            )
    require_e2e_available(
        not path_problems,
        "Missing E2E prerequisite paths: " + "; ".join(path_problems),
    )

    if docker:
        try:
            daemon_ok = _docker_daemon_ok()
            daemon_detail = "ping failed"
        except Exception as exc:  # daemon unreachable, SDK missing, ...
            daemon_ok = False
            daemon_detail = f"{type(exc).__name__}: {exc}"
        require_e2e_available(
            daemon_ok,
            f"Docker daemon unavailable: {daemon_detail}",
        )

    if fonts_platform is not None:
        root_value = values.get(
            "CBROWSER_E2E_FONTS_DIR", os.environ.get("CBROWSER_E2E_FONTS_DIR")
        )
        font_dir = None
        font_problem = None
        if not root_value:
            font_problem = "CBROWSER_E2E_FONTS_DIR is unset"
        elif not Path(root_value).is_dir():
            font_problem = (
                f"CBROWSER_E2E_FONTS_DIR is not an existing directory: "
                f"{root_value!r}"
            )
        else:
            try:
                font_dir = complete_font_set_dir(fonts_platform, root_value)
            except Exception as exc:  # pragma: no cover - defensive
                font_problem = (
                    f"cannot verify {fonts_platform} font set: "
                    f"{type(exc).__name__}: {exc}"
                )
        if font_dir is None:
            font_problem = font_problem or (
                f"no complete imported {fonts_platform!r} font set "
                f"(ok=True) under {root_value!r}"
            )
        require_e2e_available(
            font_dir is not None,
            f"Missing E2E font set for platform {fonts_platform!r}: "
            f"{font_problem}",
        )
        values["_fonts_dir"] = str(font_dir)

    return values


def worker_resource_offsets(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Deterministic per-xdist-worker resource partition (t044 AC-006).

    ``gw0`` (or no worker variable) keeps the historical single-lane
    defaults; higher workers get disjoint UDP/HTTP port bases and media
    subnets so parallel lanes on one Docker daemon cannot collide.
    """
    env = os.environ if environ is None else environ
    worker = env.get("PYTEST_XDIST_WORKER", "")
    match = re.fullmatch(r"gw(\d+)", worker)
    idx = int(match.group(1)) if match else 0
    if idx > 200:
        raise ValueError(f"xdist worker index out of range: {idx} (max 200)")
    return {
        "CBROWSER_E2E_UDP_BASE": str(30000 + idx * 1000),
        "CBROWSER_E2E_HTTP_BASE": str(35000 + idx * 1000),
        "CBROWSER_E2E_MEDIA_POOL": f"10.{251 + idx}.0.0/16",
    }


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


def free_udp_port_span(
    count: int = 2,
    *,
    start: int | None = None,
    end: int | None = None,
) -> int:
    """Return a base port with ``count`` consecutive free loopback UDP ports.

    ``CBROWSER_E2E_UDP_BASE`` partitions the default span so two
    concurrent real-topology lanes on one Docker daemon cannot allocate
    the same Supervisor mux port.
    """
    import socket

    if start is None:
        start = int(os.environ.get("CBROWSER_E2E_UDP_BASE", "30000"))
    if end is None:
        end = start + 990
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
