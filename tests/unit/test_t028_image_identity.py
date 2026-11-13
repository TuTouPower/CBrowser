"""t028 AC-005: E2E required mode image identity is fail-closed.

A set image variable must hold an immutable ``sha256:`` ID that resolves
to a locally present image.  Tags, malformed digests, missing local
images and unresolvable lookups are explicit failures, and no harness
may silently load image IDs from ``.scratch`` side files.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"

VALID_ID = "sha256:" + "a" * 64


def _load_e2e_env():
    spec = importlib.util.spec_from_file_location(
        "t028_e2e_env", FIXTURES / "e2e_env.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


e2e_env = _load_e2e_env()


def test_unset_image_vars_are_not_identity_problems() -> None:
    assert e2e_env.image_identity_problems(environ={}) == []


def test_valid_local_image_id_passes_and_is_recorded_as_evidence() -> None:
    env = {"CBROWSER_STREAM_TEST_IMAGE": VALID_ID}
    assert (
        e2e_env.image_identity_problems(env, image_exists=lambda _id: True)
        == []
    )
    assert e2e_env.collect_image_identity_evidence(env) == {
        "CBROWSER_STREAM_TEST_IMAGE": VALID_ID
    }


def test_tag_value_is_rejected() -> None:
    env = {"CBROWSER_STREAM_TEST_IMAGE": "cbrowser-stream:test"}
    problems = e2e_env.image_identity_problems(
        env, image_exists=lambda _id: True
    )
    assert len(problems) == 1
    assert "not an immutable sha256 image ID" in problems[0]


def test_short_digest_is_rejected() -> None:
    env = {"CBROWSER_GATEWAY_IMAGE": "sha256:abc123"}
    problems = e2e_env.image_identity_problems(
        env, image_exists=lambda _id: True
    )
    assert len(problems) == 1
    assert "not an immutable sha256 image ID" in problems[0]


def test_locally_missing_image_is_rejected() -> None:
    env = {"CBROWSER_API_TEST_IMAGE": VALID_ID}
    problems = e2e_env.image_identity_problems(
        env, image_exists=lambda _id: False
    )
    assert problems == [
        f"CBROWSER_API_TEST_IMAGE: image not present locally: {VALID_ID}"
    ]


def test_unresolvable_lookup_is_rejected() -> None:
    def boom(_id: str) -> bool:
        raise RuntimeError("daemon down")

    env = {"CBROWSER_CADDY_TEST_IMAGE": VALID_ID}
    problems = e2e_env.image_identity_problems(env, image_exists=boom)
    assert len(problems) == 1
    assert "cannot resolve image" in problems[0]
    assert "RuntimeError" in problems[0]


def test_non_image_vars_are_ignored_by_identity_checks() -> None:
    env = {"CBROWSER_RUNTIME_ENGINE_CACHE": "not-an-image"}
    assert (
        e2e_env.image_identity_problems(env, image_exists=lambda _id: False)
        == []
    )
    assert e2e_env.collect_image_identity_evidence(env) == {}


def test_required_mode_session_fails_on_identity_problems(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E2E required mode exits 2 at collection when an image identity problem
    is present, and the report names the concrete problem (t028 AC-005)."""
    import functools

    fixtures_path = str(FIXTURES)
    if fixtures_path not in sys.path:
        sys.path.insert(0, fixtures_path)
    import e2e_prerequisites as prereq

    for name in e2e_env.REQUIRED_E2E_ENV:
        monkeypatch.setenv(name, VALID_ID)
    monkeypatch.setenv("CBROWSER_RUNTIME_ENGINE_CACHE", str(tmp_path))
    monkeypatch.setenv("CBROWSER_RUNTIME_GEOIP_CACHE", str(tmp_path))
    monkeypatch.setenv("CBROWSER_E2E_REQUIRED", "1")

    class _Marker:
        args = ("CBROWSER_GATEWAY_IMAGE",)

    class _Item:
        fspath = REPO_ROOT / "tests" / "e2e" / "test_identity_probe_e2e.py"
        path = fspath

        def iter_markers(self, name):
            return [_Marker()] if name == "e2e_images" else []

    real_collect = prereq.collect_prerequisite_problems
    monkeypatch.setattr(
        prereq,
        "collect_prerequisite_problems",
        functools.partial(
            real_collect,
            image_exists=lambda _id: False,
            docker_ping=lambda: None,
        ),
    )
    exits: list[tuple[str, int]] = []
    monkeypatch.setattr(
        prereq.pytest,
        "exit",
        lambda msg, returncode=0: exits.append((str(msg), returncode)),
    )

    prereq.enforce_e2e_prerequisites(None, [_Item()])

    assert len(exits) == 1
    assert exits[0][1] == 2
    assert "CBROWSER_GATEWAY_IMAGE" in exits[0][0]
    assert "not present locally" in exits[0][0]


def test_frontend_harness_never_loads_images_from_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A .scratch/images_env.txt must not resurrect missing env vars."""
    fixtures_path = str(FIXTURES)
    if fixtures_path not in sys.path:
        sys.path.insert(0, fixtures_path)
    import frontend_probe.harness as harness_module

    assert not hasattr(harness_module, "load_images_env")

    engine_cache = tmp_path / "engine_cache"
    geoip_cache = tmp_path / "geoip_cache"
    engine_cache.mkdir()
    geoip_cache.mkdir()
    scratch = tmp_path / ".scratch"
    scratch.mkdir()
    lines = []
    for name in e2e_env.REQUIRED_E2E_ENV:
        if e2e_env.is_image_env_var(name):
            lines.append(f"{name}={VALID_ID}")
    lines.append(f"CBROWSER_RUNTIME_ENGINE_CACHE={engine_cache}")
    lines.append(f"CBROWSER_RUNTIME_GEOIP_CACHE={geoip_cache}")
    (scratch / "images_env.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(harness_module, "REPO_ROOT", tmp_path)
    for name in e2e_env.REQUIRED_E2E_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("CBROWSER_E2E_REQUIRED", raising=False)
    # Client construction is not under test here; the SDK probes the
    # daemon eagerly, so stand it in to reach the env gate itself.
    import docker

    monkeypatch.setattr(docker, "from_env", lambda *a, **k: object())

    # With the historical side-file loader this construction proceeded;
    # fail-closed behaviour must skip on the first missing image variable.
    with pytest.raises(pytest.skip.Exception):
        harness_module.FrontendTopologyHarness(tmp_path / "work")
