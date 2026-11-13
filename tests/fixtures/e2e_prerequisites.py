"""Collection-time E2E prerequisite enforcement (t044 AC-005).

This module owns the *E2E-session* fail-closed gate only.  It is deliberately
kept out of the frontend-dist freshness hook: ``CBROWSER_E2E_REQUIRED`` is a
session-level E2E switch, and a non-E2E collection must never be affected by
it.  The dist freshness gate and this prerequisite gate are two independent
mechanisms wired from two independent collection hooks.

Contract: ``required_e2e_names`` / ``_missing_requirements`` / the pure
``collect_prerequisite_problems`` operate on the list of **real pytest Items**
collected for an E2E session.  The pure helper is the single, injectable source
of truth for the missing-item report; ``enforce_e2e_prerequisites`` is the only
place that turns that report into a ``pytest.exit``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable, Mapping

import pytest
from e2e_env import (
    REQUIRED_E2E_ENV,
    image_identity_problems,
    required_e2e_names,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_DIR = REPO_ROOT / "tests" / "e2e"
HOST_CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
_CACHE_NAMES = frozenset(
    {"CBROWSER_RUNTIME_ENGINE_CACHE", "CBROWSER_RUNTIME_GEOIP_CACHE"}
)
_FONTS_SUITE = "test_fingerprint_platform_e2e.py"
_SELKIES_SUITE = "test_frontend_adapter_build.py"


def _item_needs_host_chrome(item) -> bool:
    """True when the item's suite launches the host Google Chrome.

    Host-Chrome consumers drive Playwright with ``channel="chrome"`` (or the
    explicit CHROME_PATH constant); container-only suites never touch a host
    browser, so the Chrome prerequisite stays scoped to the suites that need
    it (t024 AC-011/A33).
    """
    try:
        source = Path(str(item.fspath)).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return 'channel="chrome"' in source or "CHROME_PATH" in source


def _missing_requirements(
    items, environ: Mapping[str, str] | None = None
) -> list[str]:
    """Missing env vars / host Chrome for a list of **real pytest Items**.

    The Items must expose ``iter_markers`` (consumed by ``required_e2e_names``)
    and ``fspath``; that is the E2E-session contract and is intentionally not
    relaxed for partial stand-ins.
    """
    env = os.environ if environ is None else environ
    missing = [
        name for name in sorted(required_e2e_names(items)) if not env.get(name)
    ]
    if (
        any(_item_needs_host_chrome(item) for item in items)
        and not HOST_CHROME_PATH.is_file()
    ):
        missing.append("Google Chrome at /Applications")
    return missing


def _default_docker_ping() -> None:
    import docker

    client = docker.from_env()
    try:
        client.ping()
    finally:
        client.close()


def _path_under_e2e_dir(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    root = E2E_DIR.resolve()
    return resolved == root or root in resolved.parents


def is_e2e_session(config, items) -> bool:
    """Whether this collection is an E2E session, judged from collected
    content/config (never from an implicit module-level flag).

    A collection counts as E2E when at least one collected Item lives under
    ``tests/e2e/`` or an explicit collection argument targets that tree.
    Non-E2E collections (unit/integration only) never trigger the gate.
    """
    for item in items:
        item_path = getattr(item, "path", None) or getattr(item, "fspath", None)
        if item_path is not None and _path_under_e2e_dir(Path(str(item_path))):
            return True
    args: tuple = ()
    if config is not None:
        args = tuple(getattr(config, "args", None) or ())
        if not args:
            getoption = getattr(config, "getoption", None)
            if getoption is not None:
                try:
                    args = tuple(getoption("file_or_dir", default=()) or ())
                except (ValueError, KeyError, TypeError):
                    args = ()
    for arg in args:
        if _path_under_e2e_dir(Path(str(arg))):
            return True
    return False


def collect_prerequisite_problems(
    items,
    *,
    environ: Mapping[str, str] | None = None,
    image_exists: Callable[[str], bool] | None = None,
    docker_ping: Callable[[], None] | None = None,
    repo_root: Path | None = None,
) -> list[str]:
    """Enumerate every missing E2E prerequisite as formatted report lines.

    Pure with respect to pytest state and process globals: no ``pytest.exit``,
    no implicit Docker daemon contact (``docker_ping`` is injectable), and all
    environment/image lookups are injectable.  ``items`` are the collected
    **real pytest Items** for an E2E session.  No prerequisite is degraded into
    a per-test skip here; the caller decides whether to exit.
    """
    env = os.environ if environ is None else environ
    root = REPO_ROOT if repo_root is None else repo_root
    required = required_e2e_names(items)
    problems: list[str] = []

    # Presence gate (t028 AC-005 / t044 AC-005): missing env vars + host Chrome.
    for name in _missing_requirements(items, environ=env):
        problems.append(f"- {name}: {REQUIRED_E2E_ENV.get(name, 'Google Chrome')}")

    # Fail-closed image identity (t028 AC-005): a set variable holding a tag,
    # a malformed digest, or an ID that does not resolve locally fails closed.
    for problem in image_identity_problems(
        environ=env, image_exists=image_exists, names=required
    ):
        problems.append(f"- {problem}")

    # Docker daemon reachability.
    try:
        (docker_ping or _default_docker_ping)()
    except Exception as exc:  # daemon unreachable or SDK absent
        problems.append(f"- Docker daemon unavailable: {type(exc).__name__}: {exc}")

    # Engine / GeoIP caches must be initialized directories.
    for name in sorted(required & _CACHE_NAMES):
        value = env.get(name)
        if not value or not Path(value).is_dir():
            problems.append(f"- {name}: not an existing directory: {value!r}")

    # Windows/macOS font sets (only suites that exercise platform fonts).
    if any(Path(str(item.fspath)).name == _FONTS_SUITE for item in items):
        fonts_root = env.get("CBROWSER_E2E_FONTS_DIR")
        if not fonts_root or not Path(fonts_root).is_dir():
            problems.append(
                "- CBROWSER_E2E_FONTS_DIR: not an existing directory: "
                f"{fonts_root!r} (windows/macos font sets unavailable)"
            )
        else:
            ok_platforms: set[str] = set()
            try:
                from cbrowser.font_sets import list_font_sets

                ok_platforms = {
                    entry["platform"]
                    for entry in list_font_sets(fonts_root)
                    if entry["integrity"]["ok"]
                }
            except Exception as exc:
                problems.append(
                    "- CBROWSER_E2E_FONTS_DIR: cannot verify font sets: "
                    f"{type(exc).__name__}: {exc}"
                )
            for platform in ("windows", "macos"):
                if platform not in ok_platforms:
                    problems.append(
                        "- CBROWSER_E2E_FONTS_DIR: missing complete imported "
                        f"{platform} font set (ok=True)"
                    )

    # Pinned local Selkies wheel (only the adapter-build suite).
    if any(Path(str(item.fspath)).name == _SELKIES_SUITE for item in items):
        from scripts import vendor_selkies_web as vendor_module

        cache = Path(
            env.get(
                "CBROWSER_SELKIES_WHEEL_CACHE",
                str(root / ".scratch" / "selkies_wheels"),
            )
        )
        wheel = cache / vendor_module.PINNED_WHEEL_FILENAME
        if not wheel.is_file():
            problems.append(f"- Local Selkies wheel cache missing: {wheel}")
        else:
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            if digest != vendor_module.PINNED_WHEEL_SHA256:
                problems.append(
                    "- Local Selkies wheel SHA256 mismatch: "
                    f"{wheel}: {vendor_module.PINNED_WHEEL_SHA256} != {digest}"
                )

    return problems


def enforce_e2e_prerequisites(config, items) -> None:
    """E2E-session fail-closed gate (t044 AC-005).

    Called only from the E2E collection-finish hook.  Non-E2E collections and
    optional (non-required) sessions are no-ops; a required E2E session lists
    every missing prerequisite at once and ``pytest.exit(returncode=2)`` — no
    prerequisite may degrade into a per-test skip.
    """
    if os.environ.get("CBROWSER_E2E_REQUIRED") != "1":
        return
    if not is_e2e_session(config, items):
        return
    problems = collect_prerequisite_problems(items)
    if problems:
        details = "\n".join(problems)
        pytest.exit(
            f"E2E required mode is missing prerequisites:\n{details}",
            returncode=2,
        )
