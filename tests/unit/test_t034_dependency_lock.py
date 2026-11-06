"""t034 AC-002/AC-003: single uv.lock source and Python version gate.

Every image/gate requirements.txt must be the deterministic `uv export`
of its dependency group; a hand-edited file or a stale lock must fail the
gate.  The gate interpreter minor must match the runtime images.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

GROUPS = {
    "api": "config/docker/api_runtime/requirements.txt",
    "gateway": "config/docker/gateway_runtime/requirements.txt",
    "supervisor": "config/docker/supervisor_runtime/requirements.txt",
    "browser": "config/docker/browser_runtime/requirements.txt",
    "stream": "config/docker/stream_runtime/requirements.txt",
    "gate": "scripts/gate-requirements.txt",
}


def _export(group: str) -> str:
    env = dict(os.environ)
    env["UV_OFFLINE"] = "1"
    env["UV_NO_SYNC"] = "1"
    # uv export needs an interpreter satisfying requires-python>=3.15;
    # the gate venv is 3.15, but a developer running this single test on
    # another interpreter can still resolve it from the repo pin.
    env.setdefault("UV_PYTHON", "3.15")
    result = subprocess.run(
        [
            "uv", "export", "--only-group", group,
            "--no-hashes", "--no-header", "--no-emit-project",
            "--no-emit-workspace", "--format", "requirements.txt",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"uv export --only-group {group} failed: "
        f"{result.stdout[-2000:]}{result.stderr[-2000:]}"
    )
    return result.stdout


def test_each_requirements_is_the_uv_lock_export() -> None:
    for group, target in GROUPS.items():
        expected = _export(group)
        actual = (REPO_ROOT / target).read_text(encoding="utf-8")
        assert actual == expected, (
            f"{target} drifted from uv.lock export of group '{group}'; "
            f"regenerate with scripts/generate_requirements.sh"
        )


def test_uv_lock_requires_python_315() -> None:
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert lock["requires-python"] == ">=3.15"
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["project"]["requires-python"] == ">=3.15"


def test_no_legacy_requirement_lists() -> None:
    assert not (REPO_ROOT / "src" / "backend" / "requirements.txt").exists()
    assert not list((REPO_ROOT / "config" / "docker").glob("*/requirements.in"))
    assert (REPO_ROOT / "uv.lock").is_file()


def test_gate_interpreter_minor_matches_images() -> None:
    """AC-003: all suites run under the image's Python minor.

    The gate venv is built from GATE_PYTHON_MINOR; if a local interpreter
    with a different minor is used, this fails with the required version.
    """
    assert sys.version_info[:2] == (3, 15), (
        f"gate suites require CPython 3.15 (same minor as runtime images), "
        f"got {sys.version_info.major}.{sys.version_info.minor}; "
        f"run scripts/run_gates.sh which pins GATE_PYTHON_MINOR=3.15"
    )


def test_gate_python_minor_matches_images() -> None:
    gates = (REPO_ROOT / "scripts" / "run_gates.sh").read_text(encoding="utf-8")
    match = re.search(r'GATE_PYTHON_MINOR="(\d+\.\d+)"', gates)
    assert match is not None, "run_gates.sh must declare GATE_PYTHON_MINOR"
    minor = match.group(1)
    assert minor == "3.15"
    for dockerfile in (REPO_ROOT / "config" / "docker").glob("*/Dockerfile"):
        text = dockerfile.read_text(encoding="utf-8")
        for base in re.findall(r"^FROM\s+python:(\d+\.\d+)-", text, re.M):
            assert base == minor, (
                f"{dockerfile.name} uses python:{base} but gate uses {minor}"
            )
