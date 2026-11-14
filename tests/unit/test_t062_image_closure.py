"""t062 SPIKE turned permanent: cross-image dependency closure.

For every runtime image, assemble the exact file tree its Dockerfile
COPY instructions produce, then import every ``cbrowser`` module in
that tree in a subprocess whose PYTHONPATH is the image's. A missing
file surfaces as an ImportError here, in the unit gate, instead of at
container start. Third-party dependencies come from the gate venv,
which approximates the images' requirements; real image builds and
readiness probes remain [deploy]-gated (AC-005).

Adding a module to the neutral ``cbrowser.shared`` package needs no
Dockerfile change anywhere: every image that ships shared ships the
whole package (asserted structurally in test_t062_boundaries).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

IMAGES = {
    "api": "config/docker/api_runtime/Dockerfile",
    "gateway": "config/docker/gateway_runtime/Dockerfile",
    "supervisor": "config/docker/supervisor_runtime/Dockerfile",
    "browser": "config/docker/browser_runtime/Dockerfile",
    "stream": "config/docker/stream_runtime/Dockerfile",
    "proxy-forwarder": "config/docker/proxy_forwarder_runtime/Dockerfile",
}


def _parse_dockerfile(path: Path) -> tuple[list[tuple[str, str]], str]:
    copies: list[tuple[str, str]] = []
    pythonpath = "/app"
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("ENV PYTHONPATH=") or stripped.startswith(
            "PYTHONPATH="
        ):
            pythonpath = stripped.split("=", 1)[1].strip().rstrip("\\")
        if not stripped.upper().startswith("COPY "):
            continue
        tokens = [t for t in stripped.split()[1:] if not t.startswith("--")]
        if any(t.startswith("--from") for t in stripped.split()[1:]):
            continue
        if len(tokens) < 2:
            continue
        *sources, dest = tokens
        for source in sources:
            copies.append((source, dest))
    return copies, pythonpath


def _assemble_tree(dockerfile: Path, tree: Path) -> Path:
    copies, pythonpath = _parse_dockerfile(dockerfile)
    for source, dest in copies:
        if not source.startswith("src/backend"):
            continue
        src = ROOT / source
        dst = tree / dest.lstrip("/")
        if src.is_dir():
            shutil.copytree(
                src,
                dst,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return tree / pythonpath.lstrip("/")


def _module_names(pythonpath_root: Path) -> list[str]:
    package_root = pythonpath_root / "cbrowser"
    names: list[str] = []
    for py_file in sorted(package_root.rglob("*.py")):
        if py_file.name == "__main__.py":
            # Entry points execute under __main__; their import graph is
            # covered through the package modules they import.
            continue
        parts = list(py_file.relative_to(pythonpath_root).parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]
        names.append(".".join(parts))
    return names


_IMPORT_SCRIPT = """
import importlib, json, sys
failures = []
for name in json.loads(sys.argv[1]):
    try:
        importlib.import_module(name)
    except Exception as exc:
        failures.append([name, type(exc).__name__, str(exc)[:200]])
print(json.dumps(failures))
"""


@pytest.mark.parametrize("image", sorted(IMAGES))
def test_image_tree_imports_cleanly(image: str, tmp_path: Path) -> None:
    pythonpath_root = _assemble_tree(ROOT / IMAGES[image], tmp_path / "tree")
    names = _module_names(pythonpath_root)
    assert names, f"no cbrowser modules assembled for {image}"
    env = dict(os.environ, PYTHONPATH=str(pythonpath_root))
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_SCRIPT, json.dumps(names)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    failures = json.loads(result.stdout.strip().splitlines()[-1])
    assert failures == [], f"{image} image closure failures: {failures}"
