"""Build-context guards for the runtime images (t024 AC-001/A1).

STATIC PRECHECK ONLY: these tests approximate dockerignore admission and
COPY-source existence; they are not the AC-001 acceptance evidence.  The
acceptance (isolated image build + in-image import/run of launch_args) is
tracked by pending p027 for a Docker-capable environment.

Every COPY source declared by a runtime Dockerfile that ships a
Dockerfile.dockerignore whitelist must actually be admitted by that
whitelist; a source silently filtered out of the context makes the image
unbuildable (the supervisor launch_args.py case).  The matcher below
encodes the semantics the repository's whitelists rely on:

- patterns are evaluated in file order, the last pattern matching the
  candidate path itself decides;
- a pattern with a trailing slash (``!src/``) only re-opens the walk into
  that directory -- files under it still need their own matching pattern;
- a slash-less directory pattern (``!src/backend``) re-includes the whole
  subtree rooted there;
- ``*`` never crosses ``/``; ``**`` matches any number of segments.

This is a deliberate approximation of docker's patternmatcher covering
the pattern shapes used in this repository, not a general engine.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKER_DIR = ROOT / "config" / "docker"


def _segment_match(pattern_segment: str, path_segment: str) -> bool:
    regex = re.escape(pattern_segment).replace(r"\*", "[^/]*")
    return re.fullmatch(regex, path_segment) is not None


def _pattern_matches_path(pattern: str, rel_path: str) -> bool:
    """True when *pattern* matches the whole relative path or a prefix dir."""
    pat_parts = [part for part in pattern.split("/") if part not in ("", ".")]
    path_parts = rel_path.split("/")
    return _match_parts(pat_parts, path_parts)


def _match_parts(pat_parts: list[str], path_parts: list[str]) -> bool:
    if not pat_parts:
        return not path_parts
    head, rest = pat_parts[0], pat_parts[1:]
    if head == "**":
        return any(
            _match_parts(rest, path_parts[skip:])
            for skip in range(len(path_parts) + 1)
        )
    if not path_parts:
        return False
    return _segment_match(head, path_parts[0]) and _match_parts(rest, path_parts[1:])


class Dockerignore:
    """Admission check with the semantics documented in the module docstring.

    A pattern decides a candidate when it matches the candidate path or one
    of its ancestor prefixes (per-segment matching, ``**`` crossing
    segments); the last deciding pattern in file order wins.  Patterns
    written with a trailing slash are directory walk gates only: they let
    the walker descend but never decide a file's own admission, so a file
    under a re-opened directory still needs its own matching pattern.
    """

    def __init__(self, text: str) -> None:
        self.rules: list[tuple[bool, str, bool]] = []  # (negated, pattern, dir_only)
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            pattern = line[1:] if negated else line
            dir_only = pattern.endswith("/")
            self.rules.append((negated, pattern.strip("/"), dir_only))

    def admits(self, rel_path: str) -> bool:
        rel = rel_path.strip("/")
        path_parts = rel.split("/")
        admitted = True
        for negated, pattern, dir_only in self.rules:
            if dir_only:
                continue
            pat_parts = [p for p in pattern.split("/") if p not in ("", ".")]
            if any(
                _match_parts(pat_parts, path_parts[:cut])
                for cut in range(1, len(path_parts) + 1)
            ):
                admitted = negated
        return admitted


def _copy_sources(dockerfile: Path) -> list[str]:
    sources: list[str] = []
    for raw in dockerfile.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.upper().startswith("COPY "):
            continue
        tokens = line.split()[1:]
        if any(tok.startswith("--from") for tok in tokens):
            continue  # source lives in a build stage, not in the context
        tokens = [tok for tok in tokens if not tok.startswith("--")]
        if len(tokens) < 2:
            continue
        sources.extend(tokens[:-1])
    return sources


def _runtime_dockerfiles() -> list[Path]:
    return sorted(DOCKER_DIR.glob("*/Dockerfile"))


def test_copy_sources_exist_in_tree() -> None:
    missing: list[str] = []
    for dockerfile in _runtime_dockerfiles():
        for source in _copy_sources(dockerfile):
            if not (ROOT / source).exists():
                missing.append(f"{dockerfile.parent.name}: {source}")
    assert not missing, "COPY sources missing from tree:\n" + "\n".join(missing)


def test_copy_sources_admitted_by_dockerignore() -> None:
    rejected: list[str] = []
    for dockerfile in _runtime_dockerfiles():
        ignore_file = dockerfile.with_name("Dockerfile.dockerignore")
        if not ignore_file.is_file():
            continue
        rules = Dockerignore(ignore_file.read_text(encoding="utf-8"))
        for source in _copy_sources(dockerfile):
            source_path = ROOT / source
            if source_path.is_dir():
                candidates = [
                    str(path.relative_to(ROOT))
                    for path in sorted(source_path.rglob("*.py"))
                ]
                if not candidates or not any(rules.admits(c) for c in candidates):
                    rejected.append(f"{dockerfile.parent.name}: dir {source}")
            elif not rules.admits(source):
                rejected.append(f"{dockerfile.parent.name}: {source}")
    assert not rejected, (
        "COPY sources filtered out of the build context:\n" + "\n".join(rejected)
    )


def test_supervisor_context_admits_every_copied_package_file() -> None:
    """The supervisor whitelist is *.py-shaped: every top-level module of a
    copied package directory must be admitted, not just the named files."""
    dockerfile = DOCKER_DIR / "supervisor_runtime" / "Dockerfile"
    rules = Dockerignore(
        (DOCKER_DIR / "supervisor_runtime" / "Dockerfile.dockerignore").read_text(
            encoding="utf-8"
        )
    )
    rejected: list[str] = []
    for source in _copy_sources(dockerfile):
        source_path = ROOT / source
        if source_path.is_dir():
            for module in sorted(source_path.glob("*.py")):
                rel = str(module.relative_to(ROOT))
                if not rules.admits(rel):
                    rejected.append(rel)
        elif source_path.suffix == ".py" and not rules.admits(source):
            rejected.append(source)
    assert not rejected, "supervisor modules filtered out:\n" + "\n".join(rejected)


def test_launch_args_module_is_importable() -> None:
    """The module AC-001 ships into the supervisor image must import cleanly
    in the gate environment (isolated-image execution is Docker-gated)."""
    import importlib

    module = importlib.import_module("cbrowser.launch_args")
    assert module is not None
