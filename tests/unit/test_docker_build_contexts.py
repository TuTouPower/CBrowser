"""Build-context guards for the runtime images (t024 AC-001/A1).

Fast static checks cover the pattern shapes used by these allowlists.
Native BuildKit admission is independently verified by
``tests/e2e/test_native_build_contexts_e2e.py``; runtime images are also built
and exercised by the Docker/Chrome gate. See finding d037 for the native
parent-directory exception behavior that this model must preserve.

Every COPY source declared by a runtime Dockerfile that ships a
Dockerfile.dockerignore whitelist must actually be admitted by that
whitelist; a source silently filtered out of the context makes the image
unbuildable (the supervisor launch_args.py case).  The matcher below
encodes the semantics the repository's whitelists rely on:

- patterns are evaluated in file order, the last pattern matching the
  candidate path itself decides;
- a directory exception (including ``!src/``) admits its descendants;
  exact file exceptions can traverse excluded parents without broadly
  admitting the parent subtree;
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

    A directory exception applies to descendants too, matching native
    Docker behavior. Whitelists should use leaf paths/globs instead of
    re-including all parent directories merely to reach those leaves.
    """

    def __init__(self, text: str) -> None:
        self.rules: list[tuple[bool, str]] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            pattern = line[1:] if negated else line
            self.rules.append((negated, pattern.strip("/")))

    def admits(self, rel_path: str) -> bool:
        rel = rel_path.strip("/")
        path_parts = rel.split("/")
        admitted = True
        for negated, pattern in self.rules:
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


def test_every_runtime_dockerfile_has_dockerignore() -> None:
    """t027 AC-002: a runtime image without ignore rules fails the gate
    instead of silently shipping the whole repository as build context."""
    missing = [
        dockerfile.parent.name
        for dockerfile in _runtime_dockerfiles()
        if not dockerfile.with_name("Dockerfile.dockerignore").is_file()
    ]
    assert not missing, (
        "runtime images missing Dockerfile.dockerignore:\n" + "\n".join(missing)
    )


def test_sensitive_paths_never_admitted_by_runtime_contexts() -> None:
    """t027 AC-002: data/, deploy secrets and scratch never enter any
    runtime build context, whatever the whitelist admits for COPY."""
    sensitive = [
        "data/instance/cbrowser.db",
        "data/instance/profiles/p1/profile/Default/Cookies",
        "config/deploy/secrets/admin_password",
        "config/deploy/secrets/supervisor_key",
        "config/deploy/compose.env",
        ".scratch/probe/run.py",
        # Bytecode is build-machine state, not source: admitting it makes
        # otherwise identical builds produce different image IDs (t032
        # repeat-deploy drill) and can ship stale code.
        "src/backend/cbrowser/__pycache__/module.cpython-312.pyc",
        "src/backend/cbrowser/stream_agent/__pycache__/agent.cpython-312.pyc",
    ]
    admitted: list[str] = []
    for dockerfile in _runtime_dockerfiles():
        ignore_file = dockerfile.with_name("Dockerfile.dockerignore")
        rules = Dockerignore(ignore_file.read_text(encoding="utf-8"))
        for rel in sensitive:
            if rules.admits(rel):
                admitted.append(f"{dockerfile.parent.name}: {rel}")
    assert not admitted, (
        "sensitive paths admitted into a build context:\n" + "\n".join(admitted)
    )


def test_copy_sources_admitted_by_dockerignore() -> None:
    rejected: list[str] = []
    for dockerfile in _runtime_dockerfiles():
        ignore_file = dockerfile.with_name("Dockerfile.dockerignore")
        if not ignore_file.is_file():
            # AC-002 (t027): missing rules are a failure, never a skip;
            # test_every_runtime_dockerfile_has_dockerignore lists them.
            rejected.append(f"{dockerfile.parent.name}: missing Dockerfile.dockerignore")
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
