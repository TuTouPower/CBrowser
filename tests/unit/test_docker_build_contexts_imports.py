"""Regression guard: every runtime image's COPY whitelist must be complete
enough to import that image's entry module.

Unit and fake-Docker tests run against the full host source tree, so they
cannot catch a module that a runtime image never COPYs into itself (the
supervisor ``cbrowser.redact`` deployment failure). These tests rebuild each
image's file tree from its ``COPY src/backend/...`` lines under ``tmp_path``
and run ``import <entry>`` in a fresh interpreter whose only project path is
that reconstructed tree.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKER_DIR = ROOT / "config" / "docker"

IMAGES = [
    "api_runtime",
    "gateway_runtime",
    "supervisor_runtime",
    "browser_runtime",
    "stream_runtime",
    "automation_probe",
]

ENTRYPOINT_MODULES = {
    "api_runtime": "cbrowser.api.main",
    "gateway_runtime": "cbrowser.gateway.__main__",
    "supervisor_runtime": "cbrowser.supervisor.runner",
    "browser_runtime": "cbrowser.runtime_agent.agent",
    "stream_runtime": "cbrowser.stream_agent.agent",
    "automation_probe": None,
}


def _logical_lines(text: str):
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1].rstrip() + " "
            continue
        yield buffer + stripped
        buffer = ""
    if buffer:
        yield buffer


def _copy_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in _logical_lines(text):
        stripped = line.strip()
        if not stripped.upper().startswith("COPY "):
            continue
        tokens = stripped.split()[1:]
        if any(token.startswith("--from") for token in tokens):
            continue
        tokens = [token for token in tokens if not token.startswith("--")]
        if len(tokens) < 2:
            continue
        destination = tokens[-1]
        for source in tokens[:-1]:
            if source == "src/backend" or source.startswith("src/backend/"):
                pairs.append((source, destination))
    return pairs


def _rebuild(rebuilt: Path, text: str) -> list[Path]:
    copied: list[Path] = []
    for source, destination in _copy_pairs(text):
        source_path = ROOT / source
        destination_path = rebuilt / destination.lstrip("/")
        if source_path.is_dir():
            for python_file in sorted(source_path.rglob("*.py")):
                target = destination_path / python_file.relative_to(source_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(python_file, target)
                copied.append(target)
        elif source_path.is_file() and source_path.suffix == ".py":
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
            copied.append(destination_path)
    return copied


def _python_root(rebuilt: Path, text: str) -> Path:
    for line in _logical_lines(text):
        stripped = line.strip()
        if not stripped.upper().startswith("ENV "):
            continue
        match = re.search(r"\bPYTHONPATH=([^\s]+)", stripped)
        if match:
            return rebuilt / match.group(1).lstrip("/")
    return rebuilt / "app"


def _parse_entry_target(text: str) -> tuple[str, str] | None:
    for line in _logical_lines(text):
        stripped = line.strip()
        if not (
            stripped.upper().startswith("CMD ")
            or stripped.upper().startswith("ENTRYPOINT ")
        ):
            continue
        bracket = stripped.find("[")
        if bracket < 0:
            continue
        try:
            command = json.loads(stripped[bracket:])
        except (ValueError, TypeError):
            continue
        if not isinstance(command, list):
            continue
        tokens = [str(token) for token in command]
        for index, token in enumerate(tokens):
            if Path(token).name not in ("python", "python3"):
                continue
            rest = tokens[index + 1 :]
            if not rest:
                break
            if rest[0] == "-m" and len(rest) > 1:
                if rest[1].startswith("cbrowser"):
                    return ("module", rest[1])
            elif rest[0].endswith(".py"):
                return ("file", rest[0])
            break
    return None


def _file_to_module(value: str) -> str | None:
    parts = [
        part
        for part in Path(value).parts
        if part not in ("/", "app", "src", "backend")
    ]
    dotted = ".".join(parts)
    dotted = dotted[:-3] if dotted.endswith(".py") else dotted
    return dotted or None


def _entry_module(image: str, text: str, python_root: Path) -> str | None:
    parsed = _parse_entry_target(text)
    if parsed is None:
        return ENTRYPOINT_MODULES[image]
    kind, value = parsed
    if kind == "file":
        return _file_to_module(value) or ENTRYPOINT_MODULES[image]
    package_dir = python_root / value.replace(".", "/")
    if (package_dir / "__main__.py").is_file():
        return value + ".__main__"
    return value


def _run_import(rebuilt: Path, python_root: Path, module: str):
    environment = {
        **os.environ,
        "PYTHONPATH": str(python_root),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=str(rebuilt),
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _module_names(python_files: list[Path], python_root: Path) -> set[str]:
    names: set[str] = set()
    for python_file in python_files:
        try:
            relative = python_file.relative_to(python_root)
        except ValueError:
            continue
        parts = list(relative.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            names.add(".".join(parts))
    return names


def _resolvable(target: str, names: set[str]) -> bool:
    parts = target.split(".")
    return any(".".join(parts[:cut]) in names for cut in range(1, len(parts) + 1))


def _assert_cbrowser_imports_resolvable(
    image: str, python_files: list[Path], python_root: Path
) -> None:
    names = _module_names(python_files, python_root)
    unresolved: list[str] = []
    statements = 0
    for python_file in python_files:
        tree = ast.parse(python_file.read_text(encoding="utf-8"), filename=str(python_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if (
                    node.level
                    or not node.module
                    or not node.module.startswith("cbrowser")
                ):
                    continue
                targets = [node.module]
            elif isinstance(node, ast.Import):
                targets = [
                    alias.name
                    for alias in node.names
                    if alias.name.startswith("cbrowser")
                ]
                if not targets:
                    continue
            else:
                continue
            statements += 1
            for target in targets:
                if not _resolvable(target, names):
                    unresolved.append(f"{python_file.name}: {target}")
    assert not unresolved, (
        f"image={image}: {statements} cbrowser import(s) checked, "
        "unresolvable inside the reconstructed build context:\n"
        + "\n".join(unresolved)
    )


@pytest.mark.parametrize("image", IMAGES, ids=IMAGES)
def test_image_build_context_imports_entry_module(image: str, tmp_path: Path) -> None:
    dockerfile = DOCKER_DIR / image / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    rebuilt = tmp_path / image
    python_files = _rebuild(rebuilt, text)
    python_root = _python_root(rebuilt, text)
    entry = _entry_module(image, text, python_root)

    if entry is None:
        assert _parse_entry_target(text) is None, (
            f"image={image}: no entry module resolved while CMD/ENTRYPOINT "
            "declares a Python entry; the fallback map is stale"
        )
        _assert_cbrowser_imports_resolvable(image, python_files, python_root)
        return

    result = _run_import(rebuilt, python_root, entry)
    missing = re.findall(r"No module named '([^']+)'", result.stderr)
    assert result.returncode == 0, (
        f"image={image}: import {entry} failed in the reconstructed build "
        f"context (a module is missing from this image's COPY whitelist). "
        f"missing module(s): {', '.join(missing) or 'unknown'}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_deleting_linked_module_breaks_supervisor_import(tmp_path: Path) -> None:
    image = "supervisor_runtime"
    dockerfile = DOCKER_DIR / image / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    rebuilt = tmp_path / image
    _rebuild(rebuilt, text)
    python_root = _python_root(rebuilt, text)
    entry = _entry_module(image, text, python_root)

    redact = python_root / "cbrowser" / "redact.py"
    redact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "src" / "backend" / "cbrowser" / "redact.py", redact)

    healthy = _run_import(rebuilt, python_root, entry)
    assert healthy.returncode == 0, (
        f"image={image}: import {entry} must pass with cbrowser.redact present.\n"
        f"stdout:\n{healthy.stdout}\nstderr:\n{healthy.stderr}"
    )

    redact.unlink()
    broken = _run_import(rebuilt, python_root, entry)
    assert broken.returncode != 0, (
        f"image={image}: gate is a no-op, deleting cbrowser.redact still "
        f"allowed import {entry} to pass"
    )
    assert "ModuleNotFoundError" in broken.stderr, (
        f"image={image}: expected ModuleNotFoundError, got:\n{broken.stderr}"
    )
    assert "No module named 'cbrowser.redact'" in broken.stderr, (
        f"image={image}: failure did not name cbrowser.redact:\n{broken.stderr}"
    )
