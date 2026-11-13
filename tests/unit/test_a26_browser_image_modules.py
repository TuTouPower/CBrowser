"""A26/t068: the Browser image ships the runtime_agent import closure plus the
t068 offline fingerprint probe package.

Static import-closure analysis over the tracked Browser Dockerfile and its
dockerignore. Image build and in-image health/font/preview/CDP/download/stop
checks are Docker-gated and recorded in the adoption evidence, not here.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CBROWSER = ROOT / "src" / "backend" / "cbrowser"
DOCKERFILE = ROOT / "config" / "docker" / "browser_runtime" / "Dockerfile"
DOCKERIGNORE = ROOT / "config" / "docker" / "browser_runtime" / "Dockerfile.dockerignore"
COPY_PREFIX = "src/backend/cbrowser"

UNRELATED = {
    "adapters", "agent_executor", "api", "auth", "gateway", "services",
    "stream_agent", "supervisor", "network_config.py", "runtime_event_log.py",
    "service_errors.py", "udp_mux.py",
}

FEATURE_FILES = {
    "runtime_agent": (
        "cdp_proxy.py", "download_reconciler.py", "preview_capture.py",
        "fontconfig.py", "protocol.py", "runner.py", "agent.py", "security.py",
    ),
    "font_sets": ("manifest.py",),
}

# t068: the offline fingerprint probe is a measurement tool that must run in
# the same Linux/Xvfb/engine environment as the real Browser. It ships in the
# Browser image but is not part of the runtime_agent import closure.
PROBE_PACKAGES = {"fingerprint_verification"}


def _top_level_cbrowser_refs(py_file: Path) -> set[str]:
    refs: set[str] = set()
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    containing = ["cbrowser", *py_file.relative_to(CBROWSER).parts[:-1]]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = containing[: len(containing) - node.level + 1]
                if node.module:
                    base = [*base, *node.module.split(".")]
                if len(base) > 1 and base[0] == "cbrowser":
                    refs.add(base[1])
            elif node.module == "cbrowser":
                refs.update(alias.name.split(".")[0] for alias in node.names)
            elif node.module and node.module.startswith("cbrowser."):
                refs.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("cbrowser."):
                    refs.add(alias.name.split(".")[1])
    return refs


def _package_files(name: str) -> list[Path]:
    pkg = CBROWSER / name
    if pkg.is_dir() and (pkg / "__init__.py").exists():
        return sorted(path for path in pkg.glob("*.py"))
    module = CBROWSER / (name + ".py")
    if module.is_file():
        return [module]
    return []


# Packages shipped whole into every image whose outbound references must
# not expand this image's closure: ``shared`` is the neutral package
# (t062); its modules serve several images, so e.g. its credentials
# module referencing ``secret_files`` does not make ``secret_files`` part
# of the Browser runtime. The shared package's own dependency discipline
# (no service-package imports) is guarded by test_t062_boundaries.
TERMINAL_PACKAGES = {"shared"}


def _cbrowser_closure() -> set[str]:
    closure: set[str] = set()
    pending = ["runtime_agent"]
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        closure.add(name)
        for py_file in _package_files(name):
            for ref in _top_level_cbrowser_refs(py_file):
                if ref in closure:
                    continue
                if name in TERMINAL_PACKAGES and (CBROWSER / ref).is_dir():
                    # A terminal package's references to other packages
                    # serve the other images, not this one; only its
                    # top-level leaf modules (e.g. secret_files) travel
                    # with it into every image.
                    continue
                pending.append(ref)
    return closure


def _expected_toplevel(closure: set[str]) -> set[str]:
    expected = {"__init__.py"}
    for name in closure:
        pkg = CBROWSER / name
        if pkg.is_dir() and (pkg / "__init__.py").exists():
            expected.add(name)
        elif (CBROWSER / (name + ".py")).is_file():
            expected.add(name + ".py")
        else:
            raise AssertionError(f"closure member has no deliverable: {name}")
    return expected


def _copied_toplevel() -> set[str]:
    out: set[str] = set()
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("COPY "):
            continue
        tokens = stripped.split()[1:]
        if any(token.startswith("--from") for token in tokens):
            continue
        tokens = [token for token in tokens if not token.startswith("--")]
        if len(tokens) < 2:
            continue
        for source in tokens[:-1]:
            if source == COPY_PREFIX:
                out.update(
                    path.name for path in CBROWSER.iterdir()
                    if path.name != "__pycache__"
                )
            elif source.startswith(COPY_PREFIX + "/"):
                out.add(source[len(COPY_PREFIX) + 1:].split("/")[0])
    return out


def test_browser_image_ships_runtime_closure_and_offline_probe() -> None:
    """t068: the old 'only import closure' assertion was retired wholesale
    (see progress.md). The image now additionally ships the offline
    fingerprint probe; this test covers the new deliverable set and still
    rejects anything outside closure + probe packages."""
    expected = _expected_toplevel(_cbrowser_closure()) | PROBE_PACKAGES
    assert _copied_toplevel() == expected
    for package in PROBE_PACKAGES:
        assert (CBROWSER / package / "__init__.py").is_file(), (
            f"offline probe package missing: {package}"
        )


def test_browser_image_omits_unrelated_service_entries() -> None:
    assert not (_copied_toplevel() & UNRELATED)


def test_required_runtime_features_present() -> None:
    copied = _copied_toplevel()
    assert {
        "__init__.py", "launch_args.py", "preview.py", "domain", "font_sets",
        "runtime_agent",
    } <= copied
    for package, files in FEATURE_FILES.items():
        for filename in files:
            assert (CBROWSER / package / filename).is_file(), (
                f"missing runtime feature source: {package}/{filename}"
            )


def test_dockerignore_no_longer_admits_entire_backend() -> None:
    rules = [
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    joined = "\n".join(rules)
    assert f"!{COPY_PREFIX}/**" not in rules
    for service in (
        "api", "gateway", "supervisor", "auth", "adapters", "services",
        "stream_agent", "agent_executor",
    ):
        assert f"!{COPY_PREFIX}/{service}" not in joined


def _importable_modules(closure: set[str]) -> list[str]:
    names = {"cbrowser"}
    for name in closure:
        pkg = CBROWSER / name
        if pkg.is_dir() and (pkg / "__init__.py").exists():
            names.add(f"cbrowser.{name}")
            for py_file in sorted(pkg.glob("*.py")):
                if py_file.stem not in ("__init__", "__main__"):
                    names.add(f"cbrowser.{name}.{py_file.stem}")
        else:
            names.add(f"cbrowser.{name}")
    return sorted(names)


def test_runtime_closure_imports_cleanly() -> None:
    for name in _importable_modules(_cbrowser_closure()):
        importlib.import_module(name)
