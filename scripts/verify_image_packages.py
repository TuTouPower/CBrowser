"""Verify a built image's installed Python packages match its uv.lock export.

Called by the release/E2E verification path (t034 AC-002).  uv export emits
environment markers for platform-specific packages (e.g. pywin32 is win32
only), so both sides are normalised to a set of ``name==version`` pins with
markers stripped and non-matching platform markers dropped before comparing.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

from packaging.markers import Marker

logger = logging.getLogger(__name__)

# Target environment of the runtime images (Linux/CPython 3.15 containers).
TARGET_ENV = {
    "sys_platform": "linux",
    "platform_system": "Linux",
    "platform_python_implementation": "CPython",
    "implementation_name": "cpython",
    "python_version": "3.15",
    "python_full_version": "3.15.2",
    "os_name": "posix",
    "implementation_version": "3.15.2",
    "platform_machine": "aarch64",
    "platform_release": "",
    "platform_version": "",
}


def normalise(lines: list[str], environment: dict[str, str] | None = None) -> set[str]:
    """Reduce requirement lines to pins installable in the target image.

    PEP 508 markers are evaluated against the Linux/CPython 3.15 target,
    so platform-specific pins (e.g. win32-only pywin32 or a future darwin
    extra) are excluded rather than hard-coded by string matching.
    """
    environment = TARGET_ENV if environment is None else environment
    if TARGET_ENV.keys() - environment.keys():
        raise ValueError("incomplete target marker environment")
    result: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("#", "-")):
            continue
        marker = ""
        if ";" in line:
            line, marker = line.split(";", 1)
            marker = marker.strip()
        if "==" not in line:
            continue
        if marker and not Marker(marker).evaluate(environment={**environment, "extra": ""}):
            continue
        name, version = line.split("==", 1)
        name = name.strip().lower().replace("_", "-")
        version = version.strip()
        result.add(f"{name}=={version}")
    return result


def image_freeze(image: str) -> list[str]:
    proc = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "sh", image,
         "-c", "pip freeze || /opt/venv/bin/pip freeze"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pip freeze failed in {image} (rc={proc.returncode}): "
            f"{(proc.stdout + proc.stderr)[-1000:]}"
        )
    return proc.stdout.splitlines()


def image_environment(image: str) -> dict[str, str]:
    """Read all PEP 508 environment keys from the selected image itself."""
    code = """import json, os, platform, sys
v = sys.implementation.version
iv = f"{v.major}.{v.minor}.{v.micro}"
if v.releaselevel != "final": iv += v.releaselevel[0] + str(v.serial)
print(json.dumps(dict(os_name=os.name, sys_platform=sys.platform,
    platform_machine=platform.machine(), platform_release=platform.release(),
    platform_system=platform.system(), platform_version=platform.version(),
    platform_python_implementation=platform.python_implementation(),
    python_version=platform.python_version_tuple()[0]+"."+platform.python_version_tuple()[1],
    python_full_version=platform.python_version(), implementation_name=sys.implementation.name,
    implementation_version=iv)))
"""
    proc = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python3", image, "-c", code],
        capture_output=True, text=True, timeout=180, check=False,
    )
    if proc.returncode:
        raise RuntimeError(f"target marker environment unavailable: {proc.stderr[-1000:]}")
    return json.loads(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--requirements", required=True)
    args = parser.parse_args()

    try:
        environment = image_environment(args.image)
        expected = normalise(
            Path(args.requirements).read_text(encoding="utf-8").splitlines(), environment
        )
        actual = normalise(image_freeze(args.image), environment)
    except (ValueError, RuntimeError) as exc:
        logger.error("FAIL %s: %s", args.image, exc)
        return 1
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        logger.error("FAIL %s: missing=%s extra=%s", args.image, missing, extra)
        return 1
    logger.info("OK %s: %d packages match uv.lock export", args.image, len(actual))
    return 0


if __name__ == "__main__":
    sys.exit(main())
