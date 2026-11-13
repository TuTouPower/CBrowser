"""t051 AC-019 (A55): no product-generation identifiers in current surfaces.

The product has no generation: the default data root, current docs,
source and scripts must not carry a ``v2`` self-reference. A new one
fails this test.

Scope: .env.example, README.md, CHANGELOG.md, DOCKER_DEPLOYMENT.md,
.gitignore, docs/blueprint/, docs/specs/, docs/guides/, src/, scripts/,
config/, compose.yaml, tests/.

Not scanned (historical record, not a current surface): docs/archive/,
docs/tasks/, docs/reviews/, docs/pending/, docs/handoff.md,
.repo_template/, node_modules, __pycache__.

Deliberate exceptions (legacy-path references, not generation
self-references):
- scripts/deploy.sh: the AC-004 legacy-database check names the old data
  root ``data/v2/cbrowser.db`` because that is where the pre-t051
  database actually lives; the check must name the real path to detect
  it. Covered by the t027 release-controller tests.
- tests/unit/test_t027_release_controller.py: asserts deploy.sh reports
  that legacy path (AC-004).
- docs/specs/release_deployment.md: the AC-004 contract names the same
  legacy path (the old default data root) so the behaviour is testable
  from the spec; it is the same legacy-path reference, not a generation
  self-reference.

What is NOT an exception: library versions (Pydantic v2, SQLAlchemy
2.0/2.1), the API ``version="2.0.0"`` and SemVer release headers
(``[2.0.0]``), API ``/api/v1`` -- none of the patterns below match those.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

PATTERNS = [
    "data/v2",
    "baseline_v2",
    "test-v2",
    "CBrowser v2",
    "v2 deployment",
    "v2 五服务",
    "v2 架构",
    "v2 前端",
    "v2 backend",
    "v2 入口",
    "v2 系统",
    "v2 Profile",
    "v2 用户",
    "API v2",
    "for CBrowser v2",
]

SCAN_TARGETS = [
    ".env.example",
    "README.md",
    "CHANGELOG.md",
    "DOCKER_DEPLOYMENT.md",
    ".gitignore",
    "docs/blueprint",
    "docs/specs",
    "docs/guides",
    "src",
    "scripts",
    "config",
    "compose.yaml",
    "tests",
]

# file (repo-relative) -> patterns allowed there, with the reason in the
# module docstring. Keep this empty except for the documented legacy-path
# references; any new entry needs its reason written above.
ALLOWED: dict[str, set[str]] = {
    "scripts/deploy.sh": {"data/v2"},
    "tests/unit/test_t027_release_controller.py": {"data/v2"},
    "docs/specs/release_deployment.md": {"data/v2"},
}

# This test file itself names every pattern (in PATTERNS and the docstring
# above); it is the detector, not a surface.
SKIP_FILES = {"tests/unit/test_t051_generation_hygiene.py"}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".woff", ".woff2",
    ".ttf", ".otf", ".pyc", ".pyo", ".so", ".dylib", ".zip", ".tar", ".gz",
}


def _scan_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    targets = [Path(target) for target in SCAN_TARGETS]
    files: list[Path] = []
    for chunk in completed.stdout.split(b"\0"):
        if not chunk:
            continue
        rel = Path(os.fsdecode(chunk))
        if rel.suffix.lower() in SKIP_SUFFIXES:
            continue
        if not any(rel == target or target in rel.parents for target in targets):
            continue
        files.append(REPO_ROOT / rel)
    return files


def test_no_generation_identifiers_in_current_surfaces() -> None:
    hits: list[str] = []
    for path in _scan_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        if rel in SKIP_FILES:
            continue
        allowed = ALLOWED.get(rel, set())
        for pattern in PATTERNS:
            if pattern in allowed:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    hits.append(f"{rel}:{lineno}: {pattern!r}: {line.strip()}")
    assert not hits, (
        "product-generation identifiers found in current surfaces:\n"
        + "\n".join(hits)
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")


def _relative_paths(paths: list[Path], root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in paths}


def test_scan_files_excludes_gitignored_deploy_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("config/deploy/releases/\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "clean.env").write_text(
        "CBROWSER_DATA_ROOT=data/current\n", encoding="utf-8"
    )
    _git(tmp_path, "add", "config/clean.env")
    releases = tmp_path / "config" / "deploy" / "releases"
    releases.mkdir(parents=True)
    (releases / "fake.env").write_text(
        "CBROWSER_DATA_ROOT=.../data/v2\n", encoding="utf-8"
    )
    _git(tmp_path, "check-ignore", "config/deploy/releases/fake.env")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    scanned = _relative_paths(_scan_files(), tmp_path)
    assert "config/clean.env" in scanned
    assert "config/deploy/releases/fake.env" not in scanned


def test_scan_files_includes_tracked_hit_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    (tmp_path / "config").mkdir()
    hit = tmp_path / "config" / "hit.env"
    hit.write_text("CBROWSER_DATA_ROOT=.../data/v2\n", encoding="utf-8")
    _git(tmp_path, "add", "config/hit.env")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    scanned = _relative_paths(_scan_files(), tmp_path)
    assert "config/hit.env" in scanned


def test_scan_files_fails_closed_when_git_ls_files_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_repo = tmp_path / "no_repo"
    no_repo.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", no_repo)
    with pytest.raises(subprocess.CalledProcessError):
        _scan_files()

    def unavailable(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", unavailable)
    with pytest.raises(FileNotFoundError):
        _scan_files()


def test_allowed_legacy_path_exceptions_still_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    for rel in ALLOWED:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("legacy = data/v2/cbrowser.db\n", encoding="utf-8")
        _git(tmp_path, "add", rel)
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    scanned = _relative_paths(_scan_files(), tmp_path)
    assert set(ALLOWED) <= scanned
    test_no_generation_identifiers_in_current_surfaces()

    extra = "docs/specs/forbidden.md"
    (tmp_path / extra).write_text("oops data/v2 here\n", encoding="utf-8")
    _git(tmp_path, "add", extra)
    with pytest.raises(AssertionError):
        test_no_generation_identifiers_in_current_surfaces()
