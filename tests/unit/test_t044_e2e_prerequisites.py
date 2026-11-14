"""t044 AC-005 / AC-006: E2E prerequisites are fail-closed and per-worker
resources are partitioned deterministically.

``require_e2e_env`` must abort a required-mode run and skip an optional one
for every class of missing prerequisite, always naming the missing items.
``worker_resource_offsets`` must give each xdist worker a disjoint, stable
UDP/HTTP base and media subnet while keeping the single-lane defaults.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
from cbrowser.font_sets import import_font_set

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"

_MANAGED_ENV = (
    "CBROWSER_E2E_REQUIRED",
    "CBROWSER_RUNTIME_TEST_IMAGE",
    "CBROWSER_E2E_FONTS_DIR",
    "CBROWSER_RUNTIME_ENGINE_CACHE",
    "CBROWSER_RUNTIME_GEOIP_CACHE",
    "PYTEST_XDIST_WORKER",
    "CBROWSER_E2E_UDP_BASE",
    "CBROWSER_E2E_HTTP_BASE",
    "CBROWSER_E2E_MEDIA_POOL",
)


def _load_e2e_env():
    spec = importlib.util.spec_from_file_location(
        "t044_e2e_env", FIXTURES / "e2e_env.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


e2e_env = _load_e2e_env()


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    for name in _MANAGED_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fonts_root(tmp_path, monkeypatch):
    source = tmp_path / "src"
    source.mkdir()
    (source / "arial.ttf").write_bytes(b"FONT:arial")
    (source / "calibri.ttf").write_bytes(b"FONT:calibri")
    root = tmp_path / "fonts"
    result = import_font_set(
        "windows", [str(source)], "win11-test", root=str(root)
    )
    monkeypatch.setenv("CBROWSER_E2E_FONTS_DIR", str(root))
    return root, result["dir"]


def _fake_docker_module(ping_ok: bool):
    module = types.ModuleType("docker")

    class _Client:
        def ping(self):
            if not ping_ok:
                raise RuntimeError("daemon down")
            return True

        def close(self):
            return None

    module.from_env = lambda *args, **kwargs: _Client()
    return module


def test_missing_var_fails_in_required_mode(monkeypatch):
    monkeypatch.setenv("CBROWSER_E2E_REQUIRED", "1")
    with pytest.raises(pytest.fail.Exception) as caught:
        e2e_env.require_e2e_env("CBROWSER_RUNTIME_TEST_IMAGE")
    assert "CBROWSER_RUNTIME_TEST_IMAGE" in str(caught.value)


def test_missing_var_skips_in_optional_mode(monkeypatch):
    with pytest.raises(pytest.skip.Exception) as caught:
        e2e_env.require_e2e_env("CBROWSER_RUNTIME_TEST_IMAGE")
    assert "CBROWSER_RUNTIME_TEST_IMAGE" in str(caught.value)


def test_present_var_is_returned_unchanged(monkeypatch):
    monkeypatch.setenv("CBROWSER_RUNTIME_TEST_IMAGE", "sha256:abc")
    assert e2e_env.require_e2e_env("CBROWSER_RUNTIME_TEST_IMAGE") == {
        "CBROWSER_RUNTIME_TEST_IMAGE": "sha256:abc"
    }


def test_missing_path_fails_in_required_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("CBROWSER_E2E_REQUIRED", "1")
    monkeypatch.setenv(
        "CBROWSER_RUNTIME_ENGINE_CACHE", str(tmp_path / "missing")
    )
    with pytest.raises(pytest.fail.Exception) as caught:
        e2e_env.require_e2e_env(
            "CBROWSER_RUNTIME_ENGINE_CACHE",
            paths=("CBROWSER_RUNTIME_ENGINE_CACHE",),
        )
    assert "CBROWSER_RUNTIME_ENGINE_CACHE" in str(caught.value)


def test_missing_path_skips_in_optional_mode(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "CBROWSER_RUNTIME_ENGINE_CACHE", str(tmp_path / "missing")
    )
    with pytest.raises(pytest.skip.Exception) as caught:
        e2e_env.require_e2e_env(
            "CBROWSER_RUNTIME_ENGINE_CACHE",
            paths=("CBROWSER_RUNTIME_ENGINE_CACHE",),
        )
    assert "CBROWSER_RUNTIME_ENGINE_CACHE" in str(caught.value)


def test_existing_path_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("CBROWSER_RUNTIME_ENGINE_CACHE", str(tmp_path))
    values = e2e_env.require_e2e_env(
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        paths=("CBROWSER_RUNTIME_ENGINE_CACHE",),
    )
    assert values["CBROWSER_RUNTIME_ENGINE_CACHE"] == str(tmp_path)


def test_docker_unavailable_fails_in_required_mode(monkeypatch):
    monkeypatch.setenv("CBROWSER_E2E_REQUIRED", "1")
    monkeypatch.setitem(sys.modules, "docker", _fake_docker_module(False))
    with pytest.raises(pytest.fail.Exception) as caught:
        e2e_env.require_e2e_env(docker=True)
    assert "Docker daemon unavailable" in str(caught.value)


def test_docker_unavailable_skips_in_optional_mode(monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", _fake_docker_module(False))
    with pytest.raises(pytest.skip.Exception) as caught:
        e2e_env.require_e2e_env(docker=True)
    assert "Docker daemon unavailable" in str(caught.value)


def test_docker_available_passes(monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", _fake_docker_module(True))
    assert e2e_env.require_e2e_env(docker=True) == {}


def test_fonts_platform_resolves_imported_set(fonts_root):
    _root, set_dir = fonts_root
    values = e2e_env.require_e2e_env(fonts_platform="windows")
    assert values["_fonts_dir"] == set_dir
    assert Path(values["_fonts_dir"]).is_dir()


def test_fonts_platform_missing_fails_in_required_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("CBROWSER_E2E_REQUIRED", "1")
    root = tmp_path / "empty_fonts"
    root.mkdir()
    monkeypatch.setenv("CBROWSER_E2E_FONTS_DIR", str(root))
    with pytest.raises(pytest.fail.Exception) as caught:
        e2e_env.require_e2e_env(fonts_platform="macos")
    assert "macos" in str(caught.value)


def test_fonts_platform_missing_skips_in_optional_mode(tmp_path, monkeypatch):
    root = tmp_path / "empty_fonts"
    root.mkdir()
    monkeypatch.setenv("CBROWSER_E2E_FONTS_DIR", str(root))
    with pytest.raises(pytest.skip.Exception) as caught:
        e2e_env.require_e2e_env(fonts_platform="macos")
    assert "macos" in str(caught.value)


def test_require_e2e_available_routes_both_modes(monkeypatch):
    monkeypatch.setenv("CBROWSER_E2E_REQUIRED", "1")
    with pytest.raises(pytest.fail.Exception) as caught:
        e2e_env.require_e2e_available(False, "missing item X")
    assert "missing item X" in str(caught.value)
    monkeypatch.delenv("CBROWSER_E2E_REQUIRED")
    with pytest.raises(pytest.skip.Exception):
        e2e_env.require_e2e_available(False, "missing item X")
    assert e2e_env.require_e2e_available(True, "ignored") is None


def test_worker_resource_offsets_are_distinct_and_deterministic():
    offsets = [
        e2e_env.worker_resource_offsets(
            environ={"PYTEST_XDIST_WORKER": worker}
        )
        for worker in ("gw0", "gw1", "gw2")
    ]
    assert offsets[0] == {
        "CBROWSER_E2E_UDP_BASE": "30000",
        "CBROWSER_E2E_HTTP_BASE": "35000",
        "CBROWSER_E2E_MEDIA_POOL": "10.251.0.0/16",
        "CBROWSER_E2E_INSTANCE_ID": "e2e-lane-0",
    }
    assert offsets[1] == {
        "CBROWSER_E2E_UDP_BASE": "31000",
        "CBROWSER_E2E_HTTP_BASE": "36000",
        "CBROWSER_E2E_MEDIA_POOL": "10.252.0.0/16",
        "CBROWSER_E2E_INSTANCE_ID": "e2e-lane-1",
    }
    assert offsets[2] == {
        "CBROWSER_E2E_UDP_BASE": "32000",
        "CBROWSER_E2E_HTTP_BASE": "37000",
        "CBROWSER_E2E_MEDIA_POOL": "10.253.0.0/16",
        "CBROWSER_E2E_INSTANCE_ID": "e2e-lane-2",
    }
    assert len({o["CBROWSER_E2E_UDP_BASE"] for o in offsets}) == 3
    assert len({o["CBROWSER_E2E_HTTP_BASE"] for o in offsets}) == 3
    assert len({o["CBROWSER_E2E_MEDIA_POOL"] for o in offsets}) == 3
    assert (
        e2e_env.worker_resource_offsets(
            environ={"PYTEST_XDIST_WORKER": "gw1"}
        )
        == offsets[1]
    )


def test_worker_resource_offsets_default_without_worker():
    assert e2e_env.worker_resource_offsets(environ={}) == {
        "CBROWSER_E2E_UDP_BASE": "30000",
        "CBROWSER_E2E_HTTP_BASE": "35000",
        "CBROWSER_E2E_MEDIA_POOL": "10.251.0.0/16",
        "CBROWSER_E2E_INSTANCE_ID": "e2e-lane-0",
    }


def test_worker_resource_offsets_non_worker_name_uses_default():
    assert (
        e2e_env.worker_resource_offsets(
            environ={"PYTEST_XDIST_WORKER": "master"}
        )["CBROWSER_E2E_UDP_BASE"]
        == "30000"
    )


def test_worker_resource_offsets_reject_out_of_range_worker():
    with pytest.raises(ValueError):
        e2e_env.worker_resource_offsets(
            environ={"PYTEST_XDIST_WORKER": "gw201"}
        )


def test_worker_resource_offsets_reject_gw5_octet_overflow():
    with pytest.raises(ValueError):
        e2e_env.worker_resource_offsets(environ={"PYTEST_XDIST_WORKER": "gw5"})


def test_pytest_configure_repartitions_inherited_ports_on_workers(monkeypatch):
    """AC-003: a worker must overwrite the controller's inherited base."""
    import importlib.util
    import os

    spec = importlib.util.spec_from_file_location(
        "e2e_conftest", REPO_ROOT / "tests" / "e2e" / "conftest.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Simulate the xdist controller having seeded defaults that the worker
    # inherited through its environment before pytest_configure runs.
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw2")
    monkeypatch.setenv("CBROWSER_E2E_UDP_BASE", "30000")
    monkeypatch.setenv("CBROWSER_E2E_HTTP_BASE", "35000")
    monkeypatch.setenv("CBROWSER_E2E_MEDIA_POOL", "10.251.0.0/16")
    monkeypatch.setenv("CBROWSER_UDP_MUX_MIN_PORT", "30000")
    monkeypatch.setenv("CBROWSER_UDP_MUX_MAX_PORT", "30991")

    mod.pytest_configure(None)

    assert os.environ["CBROWSER_E2E_UDP_BASE"] == "32000"
    assert os.environ["CBROWSER_E2E_HTTP_BASE"] == "37000"
    assert os.environ["CBROWSER_E2E_MEDIA_POOL"] == "10.253.0.0/16"
    assert os.environ["CBROWSER_UDP_MUX_MIN_PORT"] == "32000"
    assert os.environ["CBROWSER_UDP_MUX_MAX_PORT"] == "32991"
