"""t044: uv.lock/image package verification boundaries."""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "verify_image_packages.py"

_spec = importlib.util.spec_from_file_location("t044_verify_image_packages", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_vip = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _vip
_spec.loader.exec_module(_vip)
normalise = _vip.normalise
image_freeze = _vip.image_freeze
compare_packages = _vip.compare_packages
main = _vip.main
TARGET_ENV = _vip.TARGET_ENV


def test_normalise_skips_comments_blank_and_unpinned_lines():
    lines = [
        "# whole-line comment",
        "",
        "   ",
        "-r extras.txt",
        "-e .",
        "Flask",
        "requests>=2.0",
        "Foo_Bar==2.0",
        "baz==3.0; sys_platform == 'linux'",
    ]
    assert normalise(lines) == {"foo-bar==2.0", "baz==3.0"}


def test_normalise_filters_pep508_markers_against_target_env():
    lines = [
        "pywin32==312; sys_platform == 'win32'",
        "pyobjc==10.0; sys_platform == 'darwin'",
        "colorama==0.4.6; sys_platform == 'win32'",
        "linuxonly==1.0; sys_platform == 'linux'",
        "cpythononly==1.0; implementation_name == 'cpython'",
        "modern==1.0; python_version >= '3.15'",
        "legacy==1.0; python_version < '3.15'",
    ]
    assert normalise(lines) == {
        "linuxonly==1.0",
        "cpythononly==1.0",
        "modern==1.0",
    }
    assert TARGET_ENV["sys_platform"] == "linux"
    assert TARGET_ENV["python_version"] == "3.15"


def test_image_freeze_runs_docker_pip_freeze_with_timeout():
    proc = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="foo==1.0\nbar==2.0\n", stderr=""
    )
    with patch("subprocess.run", return_value=proc) as run:
        lines = image_freeze("stream:test")

    run.assert_called_once()
    args, kwargs = run.call_args
    cmd = args[0]
    assert cmd[:5] == ["docker", "run", "--rm", "--entrypoint", "sh"]
    assert "stream:test" in cmd
    assert any("pip list --format=freeze" in part for part in cmd)
    assert not any("pip freeze ||" in part for part in cmd)
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 180
    assert lines == ["foo==1.0", "bar==2.0"]


def test_image_freeze_raises_runtime_error_on_nonzero_exit():
    proc = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="boom"
    )
    with patch("subprocess.run", return_value=proc):
        with pytest.raises(RuntimeError):
            image_freeze("stream:test")


def test_image_freeze_fails_closed_on_pip_list_failure(monkeypatch):
    proc = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="pip list failed"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: proc)
    with pytest.raises(RuntimeError) as exc:
        image_freeze("stream:test")
    assert "rc=1" in str(exc.value)
    assert "pip list failed" in str(exc.value)


def _write_requirements(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "requirements.txt"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "freeze_lines",
    [
        ["foo==1.0"],
        ["foo==1.0", "bar==2.0", "baz==3.0"],
        ["bar==2.0", "baz==3.0"],
    ],
)
def test_main_returns_1_when_packages_differ(tmp_path, monkeypatch, freeze_lines):
    req = _write_requirements(tmp_path, "foo==1.0\nbar==2.0\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_image_packages.py",
            "--image",
            "stream:test",
            "--requirements",
            str(req),
        ],
    )
    with patch.object(_vip, "image_freeze", return_value=freeze_lines):
        assert main() == 1


def test_main_returns_0_when_all_packages_match(tmp_path, monkeypatch):
    req = _write_requirements(tmp_path, "foo==1.0\nbar==2.0\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_image_packages.py",
            "--image",
            "stream:test",
            "--requirements",
            str(req),
        ],
    )
    with patch.object(_vip, "image_freeze", return_value=["bar==2.0", "foo==1.0"]):
        assert main() == 0


def test_compare_packages_uses_specifier_semantics():
    expected = {"foo==1.0", "selkies==2.2.1"}
    local_build = {"foo==1.0", "selkies==2.2.1+cbrowser.1"}
    assert compare_packages(expected, local_build) == ([], [])
    higher = {"selkies==2.2.2"}
    assert compare_packages(expected, higher) == (["foo==1.0", "selkies==2.2.1"], [])
    with_extra = {*local_build, "rogue==9.9"}
    assert compare_packages(expected, with_extra) == ([], ["rogue==9.9"])


def test_local_version_satisfies_export_pin(tmp_path, monkeypatch):
    req = _write_requirements(tmp_path, "selkies==2.2.1\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_image_packages.py",
            "--image",
            "stream:test",
            "--requirements",
            str(req),
        ],
    )
    with patch.object(_vip, "image_freeze", return_value=["selkies==2.2.1+cbrowser.1"]):
        assert main() == 0


def test_version_outside_export_pin_is_reported_as_missing(tmp_path, monkeypatch, caplog):
    req = _write_requirements(tmp_path, "selkies==2.2.1\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_image_packages.py",
            "--image",
            "stream:test",
            "--requirements",
            str(req),
        ],
    )
    with patch.object(_vip, "image_freeze", return_value=["selkies==2.2.2"]):
        with caplog.at_level(logging.ERROR):
            assert main() == 1
    assert "missing=['selkies==2.2.1']" in caplog.text
    assert "extra=[]" in caplog.text
    assert "selkies==2.2.2" not in caplog.text


def test_missing_and_extra_packages_are_reported(tmp_path, monkeypatch, caplog):
    req = _write_requirements(tmp_path, "foo==1.0\nbar==2.0\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_image_packages.py",
            "--image",
            "stream:test",
            "--requirements",
            str(req),
        ],
    )
    with patch.object(_vip, "image_freeze", return_value=["bar==2.0", "baz==3.0"]):
        with caplog.at_level(logging.ERROR):
            assert main() == 1
    assert "missing=['foo==1.0']" in caplog.text
    assert "extra=['baz==3.0']" in caplog.text


@pytest.fixture(autouse=True)
def target_environment_stub(monkeypatch):
    # Existing package-comparison cases retain their assertions; Docker
    # environment acquisition is exercised independently in t060.
    monkeypatch.setattr(_vip, "image_environment", lambda image: dict(TARGET_ENV))
