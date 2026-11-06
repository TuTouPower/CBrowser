"""t041: the per-profile fontconfig whitelist contains only the bound platform
font set.

Base open-source fonts stay in the image for CloakBrowser's documented
minimum install, but they are Linux-flavoured (WenQuanYi, Unifont, FreeFont,
IPAGothic, Loma) and must never be visible to a windows or macos fingerprint
Profile (plan 6.8). The t020 font_bundle semantics (per-profile WenQuanYi
bundles plus a system-config include) are obsolete; see
docs/findings/d033_platform_font_sets_isolation.md.
"""

from __future__ import annotations

import stat
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from cbrowser.runtime_agent import fontconfig as fontconfig_module
from cbrowser.runtime_agent.fontconfig import (
    BASE_FONTS_DIR,
    FONT_SET_MOUNT_ROOT,
    PROFILE_FONTCONFIG_FILENAME,
    build_fontconfig_xml,
    prepare_profile_fontconfig,
)


def _dirs(xml_text: str) -> set[str]:
    return {element.text or "" for element in ET.fromstring(xml_text).iter("dir")}


def test_font_dir_constants_live_outside_default_scan_paths() -> None:
    assert BASE_FONTS_DIR == Path("/opt/cbrowser-base-fonts")
    assert FONT_SET_MOUNT_ROOT == Path("/run/cbrowser/fonts")
    assert PROFILE_FONTCONFIG_FILENAME == "profile-fonts.conf"
    for constant in (BASE_FONTS_DIR, FONT_SET_MOUNT_ROOT):
        for default_dir in ("/usr/share/fonts", "/usr/local/share/fonts"):
            assert not str(constant).startswith(default_dir)


def test_build_xml_declares_whitelisted_dirs_and_never_includes_system_config() -> None:
    xml = build_fontconfig_xml(["/opt/a", Path("/run/b")])
    assert "/etc/fonts" not in xml
    assert "<include" not in xml
    root = ET.fromstring(xml)
    assert _dirs(xml) == {"/opt/a", "/run/b"}
    assert list(root.iter("include")) == []


def test_build_xml_is_well_formed_with_cache_dir() -> None:
    xml = build_fontconfig_xml([BASE_FONTS_DIR])
    root = ET.fromstring(xml)
    cachedir = root.find("cachedir")
    assert cachedir is not None
    assert cachedir.text == "/tmp/cbrowser-fontconfig-cache"


def test_build_xml_escapes_directory_paths() -> None:
    raw = "/opt/a&b<c"
    xml = build_fontconfig_xml([raw])
    element = ET.fromstring(xml).find("dir")
    assert element is not None
    assert element.text == raw


def test_build_xml_accepts_empty_whitelist_without_any_dir() -> None:
    """``build_fontconfig_xml([])`` yields a valid config with zero
    <dir> entries and no system include; the null-Profile fallback is decided
    by ``profile_font_dirs`` and passes ``[BASE_FONTS_DIR]`` instead."""
    xml = build_fontconfig_xml([])
    root = ET.fromstring(xml)
    assert _dirs(xml) == set()
    assert list(root.iter("include")) == []
    assert root.find("cachedir") is not None


def test_prepare_empty_dirs_writes_fontconfig_without_dirs(tmp_path: Path) -> None:
    run_dir = tmp_path / "runtime"
    result = prepare_profile_fontconfig(run_dir, [])
    assert result is not None
    assert result.name == PROFILE_FONTCONFIG_FILENAME
    assert stat.S_IMODE(result.stat().st_mode) == 0o600
    content = result.read_text(encoding="utf-8")
    assert _dirs(content) == set()
    assert "<include" not in content
    assert "/etc/fonts" not in content


def test_prepare_writes_only_the_bound_font_set_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "runtime"
    bound = FONT_SET_MOUNT_ROOT / "macos" / "set_abc"
    result = prepare_profile_fontconfig(run_dir, [bound])
    assert result is not None
    assert result.parent == run_dir
    assert stat.S_IMODE(result.stat().st_mode) == 0o600
    content = result.read_text(encoding="utf-8")
    assert "/etc/fonts" not in content
    assert "<include" not in content
    assert _dirs(content) == {str(bound)}
    assert str(BASE_FONTS_DIR) not in content


def test_prepare_write_failure_returns_none_and_leaves_no_tmp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "runtime"

    def fail_replace(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(fontconfig_module.os, "replace", fail_replace)
    assert prepare_profile_fontconfig(run_dir, [FONT_SET_MOUNT_ROOT / "windows" / "x"]) is None
    assert not (run_dir / (PROFILE_FONTCONFIG_FILENAME + ".tmp")).exists()
    assert list(run_dir.iterdir()) == []


def test_runner_uses_profile_font_dirs_with_null_fallback() -> None:
    """start() launches real Xvfb/PulseAudio/SDK processes, so the launch-arg
    wiring is verified as a source-level assertion instead of a call-level one.
    """
    from cbrowser.runtime_agent import runner as runner_module

    source = Path(runner_module.__file__).read_text(encoding="utf-8")
    assert '"--fingerprint-platform=windows"' not in source
    assert 'f"--fingerprint-platform={cfg.fingerprint_platform}"' in source
    assert "cfg.font_bundle" not in source
    assert "profile_font_dirs" in source
    assert "cfg.font_set_id" in source


def test_profile_font_dirs_bound_set_exposes_only_the_platform_set() -> None:
    from cbrowser.runtime_agent.fontconfig import profile_font_dirs

    set_id = "a" * 64
    assert profile_font_dirs("windows", set_id) == [
        FONT_SET_MOUNT_ROOT / "windows" / set_id
    ]
    assert BASE_FONTS_DIR not in profile_font_dirs("macos", set_id)


def test_profile_font_dirs_null_falls_back_to_base_fonts() -> None:
    """AC-006: with no platform font set bound, the browser must still have
    fonts. The base open-source set is the documented fallback."""
    from cbrowser.runtime_agent.fontconfig import profile_font_dirs

    assert profile_font_dirs("windows", None) == [BASE_FONTS_DIR]
    assert profile_font_dirs("macos", None) == [BASE_FONTS_DIR]
