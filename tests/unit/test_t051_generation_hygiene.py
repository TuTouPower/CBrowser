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

from pathlib import Path

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

SKIP_PARTS = {"node_modules", ".git", "__pycache__", ".venv"}
# This test file itself names every pattern (in PATTERNS and the docstring
# above); it is the detector, not a surface.
SKIP_FILES = {"tests/unit/test_t051_generation_hygiene.py"}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".woff", ".woff2",
    ".ttf", ".otf", ".pyc", ".pyo", ".so", ".dylib", ".zip", ".tar", ".gz",
}


def _scan_files() -> list[Path]:
    files: list[Path] = []
    for target in SCAN_TARGETS:
        path = REPO_ROOT / target
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if not candidate.is_file():
                    continue
                if SKIP_PARTS & set(candidate.parts):
                    continue
                if candidate.suffix.lower() in SKIP_SUFFIXES:
                    continue
                files.append(candidate)
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
