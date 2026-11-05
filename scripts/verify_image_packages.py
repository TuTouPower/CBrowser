"""Verify a built image's installed Python packages match its uv.lock export.

Called by the release/E2E verification path (t034 AC-002).  uv export emits
environment markers for platform-specific packages (e.g. pywin32 is win32
only), so both sides are normalised to a set of ``name==version`` pins with
markers stripped and non-matching platform markers dropped before comparing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from packaging.markers import Marker

# Target environment of the runtime images (Linux/CPython 3.15 containers).
TARGET_ENV = {
    "sys_platform": "linux",
    "platform_system": "Linux",
    "platform_python_implementation": "CPython",
    "implementation_name": "cpython",
    "python_version": "3.15",
    "python_full_version": "3.15.2",
    "os_name": "posix",
}


def normalise(lines: list[str]) -> set[str]:
    """Reduce requirement lines to pins installable in the target image.

    PEP 508 markers are evaluated against the Linux/CPython 3.15 target,
    so platform-specific pins (e.g. win32-only pywin32 or a future darwin
    extra) are excluded rather than hard-coded by string matching.
    """
    result: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        marker = ""
        if ";" in line:
            line, marker = line.split(";", 1)
            marker = marker.strip()
        if "==" not in line:
            continue
        if marker:
            try:
                if not Marker(marker).evaluate(environment=TARGET_ENV):
                    continue
            except Exception:  # noqa: BLE001 - unparseable marker fails closed
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
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pip freeze failed in {image} (rc={proc.returncode}): "
            f"{(proc.stdout + proc.stderr)[-1000:]}"
        )
    return proc.stdout.splitlines()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--requirements", required=True)
    args = parser.parse_args()

    expected = normalise(
        Path(args.requirements).read_text(encoding="utf-8").splitlines()
    )
    actual = normalise(image_freeze(args.image))
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        print(f"FAIL {args.image}: missing={missing} extra={extra}")
        return 1
    print(f"OK {args.image}: {len(actual)} packages match uv.lock export")
    return 0


if __name__ == "__main__":
    sys.exit(main())
