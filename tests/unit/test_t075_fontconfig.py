"""t075: fontconfig generation follows the explicit CJK switch, and an
unbound profile no longer falls back to the Linux base fonts.

This file replaces the abolished t053 locale semantics wholesale
(test_t053_fontconfig_locale.py is deleted): under t053 the *locale*
decided Chinese-font exposure (en-US rejected CJK, everything else did
not).  t075 decouples the switch from locale — exposure is exactly
``include_cjk_fonts``, for every locale — and removes the base-fonts
fallback that masked missing platform fonts (p125 root cause).
"""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from cbrowser.runtime_agent.fontconfig import (
    CHINESE_LANG_TAGS,
    FONT_SET_MOUNT_ROOT,
    build_fontconfig_xml,
    prepare_profile_fontconfig,
    profile_font_dirs,
)


def _dirs(xml_text: str) -> set[str]:
    return {element.text or "" for element in ET.fromstring(xml_text).iter("dir")}


def test_chinese_lang_tags_cover_zh_variants() -> None:
    assert set(CHINESE_LANG_TAGS) == {
        "zh",
        "zh-cn",
        "zh-tw",
        "zh-hk",
        "zh-mo",
        "zh-sg",
    }


def test_cjk_off_rejects_chinese_coverage() -> None:
    xml = build_fontconfig_xml(["/run/fonts"], include_cjk_fonts=False)
    assert xml.count("<rejectfont>") == len(CHINESE_LANG_TAGS)
    for tag in CHINESE_LANG_TAGS:
        assert f"<string>{tag}</string>" in xml


def test_cjk_on_rejects_nothing() -> None:
    xml = build_fontconfig_xml(["/run/fonts"], include_cjk_fonts=True)
    assert "<rejectfont>" not in xml


def test_profile_font_dirs_bound_set_only() -> None:
    set_id = "a" * 64
    assert profile_font_dirs("windows", set_id) == [
        FONT_SET_MOUNT_ROOT / "windows" / set_id
    ]
    assert profile_font_dirs("macos", set_id) == [
        FONT_SET_MOUNT_ROOT / "macos" / set_id
    ]


def test_profile_font_dirs_unbound_is_empty_not_base_fallback() -> None:
    """The abolished fallback returned the Linux base fonts; an unbound
    profile must now expose nothing so the Runner fails closed."""
    assert profile_font_dirs("windows", None) == []
    assert profile_font_dirs("macos", None) == []


def test_prepare_passes_switch_through(tmp_path: Path) -> None:
    run_dir = tmp_path / "runtime"
    path = prepare_profile_fontconfig(
        run_dir, ["/run/fonts"], include_cjk_fonts=False
    )
    assert path is not None
    assert "<rejectfont>" in path.read_text(encoding="utf-8")
    path = prepare_profile_fontconfig(
        run_dir, ["/run/fonts"], include_cjk_fonts=True
    )
    assert path is not None
    assert "<rejectfont>" not in path.read_text(encoding="utf-8")


# --- real fontconfig binary -------------------------------------------------

FC_LIST = shutil.which("fc-list")
CJK_FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
LATIN_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

needs_real_fontconfig = pytest.mark.skipif(
    FC_LIST is None or not CJK_FONT.is_file() or not LATIN_FONT.is_file(),
    reason="fc-list or fixture fonts unavailable",
)


def _fc_list(config_path: Path) -> str:
    env = {"FONTCONFIG_FILE": str(config_path), "PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [FC_LIST, "--format", "%{file}\n"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@needs_real_fontconfig
def test_real_fontconfig_switch_controls_cjk_visibility(tmp_path: Path) -> None:
    """Real fontconfig: the switch — not the locale — decides whether
    the CJK faces are visible.  Both directions run under the same
    en-US-style usage to prove locale no longer participates."""
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    shutil.copyfile(CJK_FONT, fonts_dir / CJK_FONT.name)
    shutil.copyfile(LATIN_FONT, fonts_dir / LATIN_FONT.name)

    off_path = prepare_profile_fontconfig(
        tmp_path / "off",
        [fonts_dir],
        include_cjk_fonts=False,
        cache_dir=tmp_path / "cache-off",
    )
    assert off_path is not None
    listed_off = _fc_list(off_path)
    assert CJK_FONT.name not in listed_off
    assert LATIN_FONT.name in listed_off

    on_path = prepare_profile_fontconfig(
        tmp_path / "on",
        [fonts_dir],
        include_cjk_fonts=True,
        cache_dir=tmp_path / "cache-on",
    )
    assert on_path is not None
    listed_on = _fc_list(on_path)
    assert CJK_FONT.name in listed_on
    assert LATIN_FONT.name in listed_on


def _fc_match(config_path: Path, pattern: str) -> str:
    env = {"FONTCONFIG_FILE": str(config_path), "PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [shutil.which("fc-match"), "--format", "%{file}\n", pattern],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@needs_real_fontconfig
def test_real_fc_match_zh_resolves_to_platform_cjk_font(tmp_path: Path) -> None:
    """t075 review f006 (replaces the deleted t053 fc-match case):
    with the switch on, a zh-cn request resolves to the platform
    set's Chinese font; with the switch off, the same request must
    not resolve to it — the reject rules, not fontconfig's fallback,
    decide.  The pattern is ``:lang=zh-cn`` (not bare ``zh``):
    fontconfig lists the CJK faces under zh-cn/zh-tw/... and does not
    treat bare ``zh`` as a superset match for them."""
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    shutil.copyfile(CJK_FONT, fonts_dir / CJK_FONT.name)
    shutil.copyfile(LATIN_FONT, fonts_dir / LATIN_FONT.name)

    on_path = prepare_profile_fontconfig(
        tmp_path / "on",
        [fonts_dir],
        include_cjk_fonts=True,
        cache_dir=tmp_path / "cache-on",
    )
    assert on_path is not None
    assert CJK_FONT.name in _fc_match(on_path, ":lang=zh-cn")

    off_path = prepare_profile_fontconfig(
        tmp_path / "off",
        [fonts_dir],
        include_cjk_fonts=False,
        cache_dir=tmp_path / "cache-off",
    )
    assert off_path is not None
    assert CJK_FONT.name not in _fc_match(off_path, ":lang=zh-cn")


@needs_real_fontconfig
def test_real_macos_set_hides_cjk_when_switch_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """t075 review f006 (replaces the deleted t053 macos case): the
    same switch semantics through the macos platform path — the CJK
    faces are hidden from the filtered view when the switch is off
    and visible when it is on."""
    import cbrowser.runtime_agent.fontconfig as fontconfig_mod

    set_id = "b" * 64
    monkeypatch.setattr(fontconfig_mod, "FONT_SET_MOUNT_ROOT", tmp_path)
    set_dir = tmp_path / "macos" / set_id
    set_dir.mkdir(parents=True)
    shutil.copyfile(CJK_FONT, set_dir / CJK_FONT.name)
    shutil.copyfile(LATIN_FONT, set_dir / LATIN_FONT.name)
    assert profile_font_dirs("macos", set_id) == [set_dir]

    off_path = prepare_profile_fontconfig(
        tmp_path / "off",
        profile_font_dirs("macos", set_id),
        include_cjk_fonts=False,
        cache_dir=tmp_path / "cache-off",
    )
    assert off_path is not None
    listed_off = _fc_list(off_path)
    assert CJK_FONT.name not in listed_off
    assert LATIN_FONT.name in listed_off

    on_path = prepare_profile_fontconfig(
        tmp_path / "on",
        profile_font_dirs("macos", set_id),
        include_cjk_fonts=True,
        cache_dir=tmp_path / "cache-on",
    )
    assert on_path is not None
    listed_on = _fc_list(on_path)
    assert CJK_FONT.name in listed_on
    assert LATIN_FONT.name in listed_on


def test_restart_after_switch_change_regenerates_fontconfig(
    tmp_path: Path,
) -> None:
    """t075 review f006 (replaces the deleted t053 restart case): a
    restart after the CJK switch changes regenerates the profile
    fontconfig from the new switch — the same run dir's file is
    rewritten, not reused from the previous generation."""
    run_dir = tmp_path / "runtime"
    first = prepare_profile_fontconfig(
        run_dir, ["/run/fonts"], include_cjk_fonts=False
    )
    assert first is not None
    assert "<rejectfont>" in first.read_text(encoding="utf-8")
    second = prepare_profile_fontconfig(
        run_dir, ["/run/fonts"], include_cjk_fonts=True
    )
    assert second is not None
    assert second == first
    assert "<rejectfont>" not in second.read_text(encoding="utf-8")
