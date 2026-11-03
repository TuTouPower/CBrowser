"""Runtime image hygiene: staged Stream build and aligned runtime locks.

t024 AC-015/A50: the Stream image must not ship a compiler toolchain or
-dev headers in its final stage, and the pydantic family must stay on one
version across every runtime lock file.

STATIC PRECHECK ONLY: these tests read Dockerfile/requirements text; they
are not the AC-015 acceptance evidence.  The acceptance (cold build of the
staged image + ldd/import checks + real media/input/clipboard runs) is
tracked by pending p027 for a Docker-capable environment.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKER_DIR = ROOT / "config" / "docker"


def _stages(dockerfile: Path) -> list[str]:
    text = dockerfile.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^FROM ", text)
    return ["FROM " + part for part in parts[1:]]


def _code_lines(stage: str) -> str:
    return "\n".join(
        line for line in stage.splitlines() if not line.strip().startswith("#")
    )


def test_stream_runtime_final_stage_has_no_build_toolchain():
    stages = _stages(DOCKER_DIR / "stream_runtime" / "Dockerfile")
    assert len(stages) >= 2, "stream runtime must be staged (builder + runtime)"
    final = _code_lines(stages[-1])
    assert "build-essential" not in final
    assert not re.search(r"\b[a-z0-9.]+-dev\b", final), "final stage installs a -dev package"
    assert "COPY --from=builder" in final


def test_stream_runtime_builder_stage_keeps_toolchain():
    stages = _stages(DOCKER_DIR / "stream_runtime" / "Dockerfile")
    builder = _code_lines(stages[0])
    assert "build-essential" in builder
    assert "/opt/venv" in builder


def _pins(requirements: Path, package: str) -> set[str]:
    versions = set()
    for line in requirements.read_text(encoding="utf-8").splitlines():
        match = re.match(rf"{re.escape(package)}==([0-9][^\s;]*)", line.strip())
        if match:
            versions.add(match.group(1))
    return versions


def test_runtime_locks_align_pydantic_family():
    for package in ("pydantic", "pydantic-core"):
        seen: dict[str, set[str]] = {}
        for requirements in sorted(DOCKER_DIR.glob("*/requirements.txt")):
            versions = _pins(requirements, package)
            if versions:
                seen[requirements.parent.name] = versions
        assert seen, f"no runtime lock pins {package}"
        merged = set().union(*seen.values())
        assert len(merged) == 1, f"{package} versions diverge across runtimes: {seen}"


def test_stream_lock_covers_stream_agent_imports():
    """Every third-party import of the stream agent (plus the dynamically
    loaded Selkies root) must be present in the stream lock."""
    import ast

    lock_text = (DOCKER_DIR / "stream_runtime" / "requirements.txt").read_text(
        encoding="utf-8"
    )
    locked = {
        re.match(r"([A-Za-z0-9_.-]+)==", line.strip()).group(1).lower().replace("-", "_")
        for line in lock_text.splitlines()
        if re.match(r"([A-Za-z0-9_.-]+)==", line.strip())
    }
    stdlib = set(__import__("sys").stdlib_module_names)
    imported: set[str] = set()
    agent_dir = ROOT / "src" / "backend" / "cbrowser" / "stream_agent"
    for module_file in agent_dir.rglob("*.py"):
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
    third_party = {name for name in imported if name not in stdlib and name != "cbrowser"}
    missing = {name for name in third_party if name.lower() not in locked}
    assert not missing, f"stream lock misses imported packages: {missing}"
    assert "selkies" in locked  # loaded dynamically by the agent at runtime
