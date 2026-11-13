"""Regression coverage for the split E2E prerequisite mechanism.

The E2E required-mode gate is now an independent, content-gated mechanism
(``tests/fixtures/e2e_prerequisites.py``) reached only from the E2E collection
finish hook.  These tests exercise its pure, injectable core without ever
contacting a real Docker daemon, and prove non-E2E collections cannot be
hijacked by ``CBROWSER_E2E_REQUIRED``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from e2e_env import REQUIRED_E2E_ENV, is_image_env_var

import e2e_prerequisites as prereq

REPO_ROOT = Path(__file__).resolve().parents[2]
VALID_ID = "sha256:" + "a" * 64

_MANAGED_ENV = (
    *REQUIRED_E2E_ENV,
    "CBROWSER_E2E_REQUIRED",
    "CBROWSER_E2E_FONTS_DIR",
    "CBROWSER_SELKIES_WHEEL_CACHE",
)


class _Marker:
    def __init__(self, name, *args):
        self.name = name
        self.args = args


class _Item:
    """Minimal stand-in implementing the real-pytest-Item contract the E2E
    prerequisite gate relies on (``iter_markers`` + ``fspath``/``path``)."""

    def __init__(self, fspath, markers=()):
        self.fspath = Path(fspath)
        self.path = Path(fspath)
        self._markers = tuple(markers)

    def iter_markers(self, name):
        return [marker for marker in self._markers if marker.name == name]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    for name in _MANAGED_ENV:
        monkeypatch.delenv(name, raising=False)


def _standin(fspath, markers=()) -> _Item:
    return _Item(fspath, markers=markers)


def _no_daemon():
    raise RuntimeError("stub daemon down")


def test_pure_function_lists_all_missing_items(tmp_path, monkeypatch):
    """AC-005: every missing prerequisite class is reported in one call.

    Env vars, image identity, Docker daemon, engine/GeoIP caches, font sets and
    the Selkies wheel are all enumerated; a fake ``image_exists`` and an
    injected failing ``docker_ping`` keep this off the real daemon.
    """
    # Two image vars that are *set* but still fail identity (one bad tag, one
    # valid ID that does not resolve locally); everything else stays unset.
    monkeypatch.setenv("CBROWSER_RUNTIME_TEST_IMAGE", VALID_ID)
    monkeypatch.setenv("CBROWSER_STREAM_TEST_IMAGE", "cbrowser-stream:tag")

    items = [
        _standin(tmp_path / "test_fingerprint_platform_e2e.py"),
        _standin(tmp_path / "test_frontend_adapter_build.py"),
        _standin(tmp_path / "test_supervisor_core_e2e.py"),
    ]

    problems = prereq.collect_prerequisite_problems(
        items,
        image_exists=lambda _id: False,
        docker_ping=_no_daemon,
        repo_root=tmp_path,
    )
    text = "\n".join(problems)
    assert problems and all(line.startswith("- ") for line in problems)

    # 1. presence gate: every other required var is listed as missing
    for name in REQUIRED_E2E_ENV:
        if name not in {"CBROWSER_RUNTIME_TEST_IMAGE", "CBROWSER_STREAM_TEST_IMAGE"}:
            assert f"- {name}:" in text
    # 2. image identity: both failure modes (t028 AC-005)
    assert "CBROWSER_RUNTIME_TEST_IMAGE: image not present locally" in text
    assert "CBROWSER_STREAM_TEST_IMAGE: not an immutable sha256 image ID" in text
    # 3. Docker daemon unreachable
    assert "Docker daemon unavailable: RuntimeError: stub daemon down" in text
    # 4. engine / GeoIP caches are not existing directories
    assert "CBROWSER_RUNTIME_ENGINE_CACHE: not an existing directory" in text
    assert "CBROWSER_RUNTIME_GEOIP_CACHE: not an existing directory" in text
    # 5. windows/macos font sets
    assert "CBROWSER_E2E_FONTS_DIR" in text
    # 6. pinned local Selkies wheel
    assert "Local Selkies wheel cache missing" in text


def test_pure_function_no_problems_when_everything_present(tmp_path, monkeypatch):
    """A fully satisfied E2E session produces an empty problem list."""
    for name in REQUIRED_E2E_ENV:
        if is_image_env_var(name):
            monkeypatch.setenv(name, VALID_ID)
        else:
            monkeypatch.setenv(name, str(tmp_path))

    problems = prereq.collect_prerequisite_problems(
        [_standin(tmp_path / "test_supervisor_core_e2e.py")],
        image_exists=lambda _id: True,
        docker_ping=lambda: None,
        repo_root=tmp_path,
    )
    assert problems == []


def test_is_e2e_session_uses_collected_content_and_config(tmp_path):
    e2e_item = _standin(prereq.E2E_DIR / "test_foo_e2e.py")
    unit_item = _standin(tmp_path / "test_unit.py")

    class _EmptyConfig:
        args = []

    assert prereq.is_e2e_session(_EmptyConfig(), [e2e_item]) is True
    assert prereq.is_e2e_session(_EmptyConfig(), [unit_item]) is False
    assert prereq.is_e2e_session(_EmptyConfig(), [unit_item, e2e_item]) is True
    assert prereq.is_e2e_session(None, [unit_item]) is False

    class _E2EArgConfig:
        args = [str(prereq.E2E_DIR)]

    # An explicit E2E collection argument is an E2E session even with no items.
    assert prereq.is_e2e_session(_E2EArgConfig(), []) is True
    assert prereq.is_e2e_session(_E2EArgConfig(), [unit_item]) is True


def test_enforcement_noops_without_required_mode(monkeypatch):
    monkeypatch.delenv("CBROWSER_E2E_REQUIRED", raising=False)
    calls = []
    monkeypatch.setattr(prereq.pytest, "exit", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(
        prereq, "collect_prerequisite_problems", lambda *a, **k: ["- x"]
    )
    item = _standin(prereq.E2E_DIR / "test_foo_e2e.py")
    prereq.enforce_e2e_prerequisites(None, [item])
    assert not calls


def test_enforcement_noops_for_non_e2e_collection(tmp_path, monkeypatch):
    """CBROWSER_E2E_REQUIRED=1 must not hijack a non-E2E collection."""
    monkeypatch.setenv("CBROWSER_E2E_REQUIRED", "1")
    calls = []
    monkeypatch.setattr(prereq.pytest, "exit", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(
        prereq, "collect_prerequisite_problems", lambda *a, **k: ["- x"]
    )

    class _Config:
        args = [str(tmp_path)]

    item = _standin(tmp_path / "test_unit.py")
    prereq.enforce_e2e_prerequisites(_Config(), [item])
    assert not calls


def test_enforcement_exits_2_listing_every_missing_item(monkeypatch):
    monkeypatch.setenv("CBROWSER_E2E_REQUIRED", "1")
    calls = []
    monkeypatch.setattr(
        prereq.pytest,
        "exit",
        lambda msg, returncode=0: calls.append((msg, returncode)),
    )
    monkeypatch.setattr(
        prereq,
        "collect_prerequisite_problems",
        lambda *a, **k: ["- A: missing", "- B: missing"],
    )
    item = _standin(prereq.E2E_DIR / "test_foo_e2e.py")
    prereq.enforce_e2e_prerequisites(None, [item])
    assert len(calls) == 1
    message, returncode = calls[0]
    assert returncode == 2
    assert "E2E required mode is missing prerequisites" in message
    assert "- A: missing" in message
    assert "- B: missing" in message


def test_enforcement_does_not_exit_when_nothing_is_missing(monkeypatch):
    monkeypatch.setenv("CBROWSER_E2E_REQUIRED", "1")
    calls = []
    monkeypatch.setattr(prereq.pytest, "exit", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(
        prereq, "collect_prerequisite_problems", lambda *a, **k: []
    )
    item = _standin(prereq.E2E_DIR / "test_foo_e2e.py")
    prereq.enforce_e2e_prerequisites(None, [item])
    assert not calls


def test_collection_finish_wires_the_prerequisite_gate(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "e2e_prereq_conftest_under_test",
        REPO_ROOT / "tests" / "e2e" / "conftest.py",
    )
    conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conftest)

    calls = []
    conftest.enforce_e2e_prerequisites = (
        lambda config, items: calls.append((config, items))
    )

    class _Session:
        config = object()
        items = ["collected-item"]

    conftest.pytest_collection_finish(_Session())
    assert calls == [(_Session.config, _Session.items)]
