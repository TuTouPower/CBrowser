"""t053 AC-006/AC-007/AC-012: fontconfig per-locale splitting and A18 fail-closed.

- An en-US Profile's fontconfig rejects every font whose fontconfig
  language coverage includes any Chinese tag (zh-*); a zh-CN Profile's
  config rejects nothing.  No other language (ja/ko/...) is rejected.
- The reject mechanism is verified against the real fontconfig binary:
  with the en-US config ``fc-list`` no longer sees a CJK .ttc, while the
  zh-CN config still does.
- A18: a bound font set whose fontconfig generation fails aborts startup
  with ``font_set_unavailable`` and never launches the browser; an
  unbound Profile keeps the existing base-fonts fallback.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from cbrowser.runtime_agent.fontconfig import (
    CHINESE_LANG_TAGS,
    FONT_SET_UNAVAILABLE,
    FontConfigUnavailableError,
    build_fontconfig_xml,
    prepare_profile_fontconfig,
    profile_font_dirs,
)

BOUND_DIR = Path("/run/cbrowser/fonts/windows/" + "a" * 64)


def test_chinese_lang_tags_cover_zh_variants() -> None:
    assert set(CHINESE_LANG_TAGS) == {
        "zh",
        "zh-cn",
        "zh-tw",
        "zh-hk",
        "zh-mo",
        "zh-sg",
    }


def test_en_us_xml_rejects_all_chinese_lang_tags() -> None:
    xml = build_fontconfig_xml([BOUND_DIR], locale="en-US")
    ET.fromstring(xml)
    for tag in CHINESE_LANG_TAGS:
        assert f"<string>{tag}</string>" in xml
    assert xml.count("<rejectfont>") == len(CHINESE_LANG_TAGS)
    assert xml.count("</rejectfont>") == len(CHINESE_LANG_TAGS)
    assert str(BOUND_DIR) in xml


def test_en_us_xml_rejects_no_other_language() -> None:
    xml = build_fontconfig_xml([BOUND_DIR], locale="en-US")
    for tag in ("ja", "ko", "zh-Hans", "zh-Hant"):
        assert f"<string>{tag}</string>" not in xml


def test_zh_cn_and_unset_locale_xml_reject_nothing() -> None:
    for locale in ("zh-CN", None):
        xml = build_fontconfig_xml([BOUND_DIR], locale=locale)
        ET.fromstring(xml)
        assert "<rejectfont>" not in xml
        assert "<selectfont>" not in xml


def test_prepare_writes_locale_aware_fontconfig(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    en_path = prepare_profile_fontconfig(run_dir, [BOUND_DIR], locale="en-US")
    assert en_path is not None
    assert "<rejectfont>" in en_path.read_text(encoding="utf-8")

    run_dir_zh = tmp_path / "run-zh"
    zh_path = prepare_profile_fontconfig(run_dir_zh, [BOUND_DIR], locale="zh-CN")
    assert zh_path is not None
    assert "<rejectfont>" not in zh_path.read_text(encoding="utf-8")


def test_unbound_base_fallback_follows_locale_too(tmp_path: Path) -> None:
    from cbrowser.runtime_agent.fontconfig import BASE_FONTS_DIR

    run_dir = tmp_path / "run"
    path = prepare_profile_fontconfig(
        run_dir, profile_font_dirs("windows", None), locale="en-US"
    )
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert str(BASE_FONTS_DIR) in text
    # The base directory holds WenQuanYi: an en-US Profile must not see it.
    assert "<rejectfont>" in text


FC_LIST = shutil.which("fc-list")
FC_MATCH = shutil.which("fc-match")
CJK_FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
LATIN_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

needs_real_fontconfig = pytest.mark.skipif(
    FC_LIST is None
    or FC_MATCH is None
    or not CJK_FONT.is_file()
    or not LATIN_FONT.is_file(),
    reason="fc-list/fc-match or fixture fonts unavailable",
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


def _fc_match(config_path: Path, pattern: str) -> tuple[str, str]:
    """Run real ``fc-match`` under a generated config; return file, family."""
    env = {"FONTCONFIG_FILE": str(config_path), "PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [FC_MATCH, "--format", "%{file}|%{family}\n", pattern],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    first = result.stdout.strip().splitlines()[0]
    matched_file, _, matched_family = first.partition("|")
    return matched_file, matched_family


def _make_platform_font_dir(root: Path, platform: str) -> Path:
    """A platform font-set directory holding the host's real fonts.

    The host ships no Microsoft YaHei / SimSun / PingFang / Hiragino
    Sans GB files, so the platform set's Chinese font is stood in for by
    the host's real CJK font (NotoSansCJK-Regular.ttc). Assertions below
    use the real file names and families present on this host; the exact
    platform names (微软雅黑/宋体, 苹方/冬青黑体) are the files shipped
    in the real platform sets and are confirmed on the user machine
    (see task.md environment skip for AC-007).
    """
    fonts_dir = root / platform
    fonts_dir.mkdir(parents=True)
    shutil.copyfile(CJK_FONT, fonts_dir / CJK_FONT.name)
    shutil.copyfile(LATIN_FONT, fonts_dir / LATIN_FONT.name)
    return fonts_dir


@needs_real_fontconfig
def test_fc_list_hides_cjk_fonts_for_en_us(tmp_path: Path) -> None:
    """Real fontconfig run: the en-US config hides the CJK .ttc faces."""
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    shutil.copyfile(CJK_FONT, fonts_dir / CJK_FONT.name)
    shutil.copyfile(LATIN_FONT, fonts_dir / LATIN_FONT.name)

    en_run = tmp_path / "en"
    en_path = prepare_profile_fontconfig(
        en_run,
        [fonts_dir],
        locale="en-US",
        cache_dir=tmp_path / "cache-en",
    )
    assert en_path is not None
    listed = _fc_list(en_path)
    assert CJK_FONT.name not in listed
    assert LATIN_FONT.name in listed

    zh_run = tmp_path / "zh"
    zh_path = prepare_profile_fontconfig(
        zh_run,
        [fonts_dir],
        locale="zh-CN",
        cache_dir=tmp_path / "cache-zh",
    )
    assert zh_path is not None
    listed_zh = _fc_list(zh_path)
    assert CJK_FONT.name in listed_zh
    assert LATIN_FONT.name in listed_zh


def _make_runner(
    root: Path,
    config: dict,
    instance_id: str = "instance_a",
    snapshot_name: str = "snapshot_a",
    version: int = 1,
) -> object:
    from cbrowser.runtime_agent.runner import BrowserRunner

    snapshot = root / f"{snapshot_name}.json"
    snapshot.write_text(
        json.dumps(
            {
                "id": snapshot_name,
                "profile_id": "profile_a",
                "version": version,
                "config": {"name": "A18 runner", **config},
                "created_at": "2026-11-11T00:00:00+08:00",
            }
        )
    )
    return BrowserRunner(
        "profile_a",
        instance_id,
        snapshot,
        root / "runtime",
        root / "profile",
        events_dir=root / "events",
        engine_cache_dir=root / "engine_cache",
    )


def _stub_launch_plumbing(monkeypatch, root: Path) -> None:
    from cbrowser.runtime_agent import runner as runner_module
    from cbrowser.runtime_agent.runner import BrowserRunner

    monkeypatch.setattr(
        BrowserRunner, "resolve_engine_binary", lambda self: root / "chrome"
    )
    monkeypatch.setattr(
        BrowserRunner,
        "setup_pulse",
        lambda self: (root / "pulse.sock", root / "pulse.cookie"),
    )
    monkeypatch.setattr(
        BrowserRunner,
        "setup_display",
        lambda self, width=1920, height=1080: root / "X99",
    )
    monkeypatch.setattr(
        runner_module, "prepare_profile_fontconfig", lambda *args, **kwargs: None
    )


def _stub_launch_plumbing_keep_fontconfig(monkeypatch, root: Path) -> None:
    """Like :func:`_stub_launch_plumbing` but keeps the real fontconfig writer.

    Used by the locale-chain tests, which assert on the generated
    fontconfig file as well as on the engine launch call.
    """
    from cbrowser.runtime_agent import runner as runner_module
    from cbrowser.runtime_agent.runner import BrowserRunner

    monkeypatch.setattr(
        BrowserRunner, "resolve_engine_binary", lambda self: root / "chrome"
    )
    monkeypatch.setattr(
        BrowserRunner,
        "setup_pulse",
        lambda self: (root / "pulse.sock", root / "pulse.cookie"),
    )
    monkeypatch.setattr(
        BrowserRunner,
        "setup_display",
        lambda self, width=1920, height=1080: root / "X99",
    )
    monkeypatch.setattr(runner_module, "seed_widevine_hint", lambda *a, **k: None)


@pytest.mark.asyncio
async def test_bound_fontconfig_failure_fails_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A18: bound set + fontconfig failure -> font_set_unavailable, no launch."""
    from cbrowser.runtime_agent import runner as runner_module

    runner = _make_runner(
        tmp_path,
        {"font_set_id": "b" * 64, "locale": "en-US"},
    )
    _stub_launch_plumbing(monkeypatch, tmp_path)

    async def _must_not_launch(*args, **kwargs):
        raise AssertionError("browser must not launch")

    monkeypatch.setattr(
        runner_module, "launch_persistent_context_async", _must_not_launch
    )
    with pytest.raises(FontConfigUnavailableError) as excinfo:
        await runner.start()
    assert str(excinfo.value) == FONT_SET_UNAVAILABLE
    assert FONT_SET_UNAVAILABLE == "font_set_unavailable"
    assert runner.fontconfig_path is None
    state = runner.event_storage.get_instance_state(
        "profile_a", "instance_a", recover_terminal=True
    )
    assert state is not None
    assert state.state == "error"
    assert state.exit_reason == FONT_SET_UNAVAILABLE


@pytest.mark.asyncio
async def test_unbound_fontconfig_failure_keeps_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A18: unbound Profile keeps the base-fonts fallback path."""
    from cbrowser.runtime_agent import runner as runner_module

    runner = _make_runner(tmp_path, {"font_set_id": None, "locale": "en-US"})
    _stub_launch_plumbing(monkeypatch, tmp_path)
    monkeypatch.setattr(runner_module, "seed_widevine_hint", lambda *a, **k: None)

    async def _launch_reached(*args, **kwargs):
        raise RuntimeError("launch reached")

    monkeypatch.setattr(
        runner_module, "launch_persistent_context_async", _launch_reached
    )
    with pytest.raises(RuntimeError, match="launch reached"):
        await runner.start()
    assert runner.fontconfig_path is None


# --- Round 1 review fixes -------------------------------------------------

@needs_real_fontconfig
@pytest.mark.parametrize("platform", ["windows", "macos"])
def test_zh_cn_fc_match_resolves_to_platform_set_chinese_font(
    tmp_path: Path, platform: str
) -> None:
    """AC-007 (mechanism, t053_test_f002): under a zh-CN config, Chinese
    text resolves to the platform set's Chinese font file.

    The host's real CJK font stands in for the platform set's Chinese
    font (see :func:`_make_platform_font_dir`): the assertion is on the
    real resolved file inside the platform directory, not on a name the
    host does not ship. The en-US half shows the same pattern resolving
    to the set's Latin font instead, proving the split is the locale.
    """
    fonts_dir = _make_platform_font_dir(tmp_path, platform)

    zh_path = prepare_profile_fontconfig(
        tmp_path / f"run-{platform}-zh",
        [fonts_dir],
        locale="zh-CN",
        cache_dir=tmp_path / f"cache-{platform}-zh",
    )
    assert zh_path is not None
    matched_file, matched_family = _fc_match(zh_path, ":lang=zh-cn")
    assert matched_file == str(fonts_dir / CJK_FONT.name)
    assert "CJK" in matched_family

    en_path = prepare_profile_fontconfig(
        tmp_path / f"run-{platform}-en",
        [fonts_dir],
        locale="en-US",
        cache_dir=tmp_path / f"cache-{platform}-en",
    )
    assert en_path is not None
    matched_file_en, _family_en = _fc_match(en_path, ":lang=zh-cn")
    assert matched_file_en == str(fonts_dir / LATIN_FONT.name)


@needs_real_fontconfig
def test_fc_list_hides_cjk_fonts_for_macos_set(tmp_path: Path) -> None:
    """AC-006 (macos case, t053_test_f003): real fc-list run against the
    macos platform set under an en-US config."""
    fonts_dir = _make_platform_font_dir(tmp_path, "macos")
    en_path = prepare_profile_fontconfig(
        tmp_path / "en",
        [fonts_dir],
        locale="en-US",
        cache_dir=tmp_path / "cache-en",
    )
    assert en_path is not None
    listed = _fc_list(en_path)
    assert CJK_FONT.name not in listed
    assert LATIN_FONT.name in listed


@needs_real_fontconfig
def test_unbound_fallback_follows_locale_in_real_fc_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-006 (unbound case, t053_test_f003): the base-fonts fallback
    directory follows the locale rule under a real fc-list run.

    The real base directory (``/opt/cbrowser-base-fonts``, WenQuanYi)
    exists only in the Browser image, so it is stood in for here by a
    directory holding the host's real CJK + Latin fonts; the production
    path (``profile_font_dirs`` -> ``prepare_profile_fontconfig`` ->
    fc-list) runs unchanged via a monkeypatched ``BASE_FONTS_DIR``.
    """
    from cbrowser.runtime_agent import fontconfig as fontconfig_module

    base_dir = tmp_path / "base-fonts"
    base_dir.mkdir()
    shutil.copyfile(CJK_FONT, base_dir / CJK_FONT.name)
    shutil.copyfile(LATIN_FONT, base_dir / LATIN_FONT.name)
    monkeypatch.setattr(fontconfig_module, "BASE_FONTS_DIR", base_dir)

    dirs = profile_font_dirs("windows", None)
    assert dirs == [base_dir]

    en_path = prepare_profile_fontconfig(
        tmp_path / "en", dirs, locale="en-US", cache_dir=tmp_path / "cache-en"
    )
    assert en_path is not None
    listed_en = _fc_list(en_path)
    assert CJK_FONT.name not in listed_en
    assert LATIN_FONT.name in listed_en

    zh_path = prepare_profile_fontconfig(
        tmp_path / "zh", dirs, locale="zh-CN", cache_dir=tmp_path / "cache-zh"
    )
    assert zh_path is not None
    listed_zh = _fc_list(zh_path)
    assert CJK_FONT.name in listed_zh
    assert LATIN_FONT.name in listed_zh


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "expect_reject"),
    [("zh-CN", False), ("en-US", True)],
)
async def test_explicit_locale_reaches_engine_launch_alongside_geoip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    locale: str,
    expect_reject: bool,
) -> None:
    """AC-009 (chain, t053_code_f001 / t053_test_f001): the Profile locale
    reaches the engine launch call verbatim, next to ``geoip=True``.

    The Runner passes ``locale=cfg.locale`` and ``geoip=cfg.geoip`` to
    ``launch_persistent_context_async`` and the same locale drives the
    generated fontconfig. Whether CloakBrowser lets that explicit locale
    win over geoip inference inside the engine is the remaining
    user-machine check (task.md unknown-contract #1, rewritten as a
    conclusion); this test pins the chain up to the engine call.
    """
    from cbrowser.runtime_agent import runner as runner_module

    runner = _make_runner(
        tmp_path,
        {"font_set_id": None, "locale": locale, "geoip": True, "timezone": None},
    )
    _stub_launch_plumbing_keep_fontconfig(monkeypatch, tmp_path)
    captured: dict = {}

    async def _capture_launch(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("launch reached")

    monkeypatch.setattr(
        runner_module, "launch_persistent_context_async", _capture_launch
    )
    with pytest.raises(RuntimeError, match="launch reached"):
        await runner.start()
    assert captured["locale"] == locale
    assert captured["geoip"] is True
    assert captured["timezone"] is None
    assert runner.fontconfig_path is not None
    text = runner.fontconfig_path.read_text(encoding="utf-8")
    assert ("<rejectfont>" in text) is expect_reject


@pytest.mark.asyncio
async def test_restart_after_locale_change_regenerates_fontconfig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-008 (runtime half, t053_test_f004): after a language change and
    restart, the Runner regenerates the fontconfig for the new language.

    A restart is a fresh BrowserRunner (new runtime instance, new config
    snapshot version) over the same profile directories. The fake launch
    records the locale each start receives; the real fontconfig writer
    runs both times. The real-engine half (``navigator.language`` inside
    the Browser) remains an environment skip, see task.md.
    """
    from cbrowser.runtime_agent import runner as runner_module

    _stub_launch_plumbing_keep_fontconfig(monkeypatch, tmp_path)
    launched: list[dict] = []

    async def _capture_launch(*args, **kwargs):
        launched.append(dict(kwargs))
        raise RuntimeError("launch reached")

    monkeypatch.setattr(
        runner_module, "launch_persistent_context_async", _capture_launch
    )

    runner_en = _make_runner(
        tmp_path,
        {"font_set_id": None, "locale": "en-US", "geoip": True},
        instance_id="instance_a",
        snapshot_name="snapshot_v1",
        version=1,
    )
    with pytest.raises(RuntimeError, match="launch reached"):
        await runner_en.start()
    assert runner_en.fontconfig_path is not None
    assert "<rejectfont>" in runner_en.fontconfig_path.read_text(
        encoding="utf-8"
    )

    # Language changed to zh-CN; the supervisor restarts the profile with
    # a new snapshot version and a new runtime instance.
    runner_zh = _make_runner(
        tmp_path,
        {"font_set_id": None, "locale": "zh-CN", "geoip": True},
        instance_id="instance_b",
        snapshot_name="snapshot_v2",
        version=2,
    )
    with pytest.raises(RuntimeError, match="launch reached"):
        await runner_zh.start()
    assert runner_zh.fontconfig_path is not None
    assert "<rejectfont>" not in runner_zh.fontconfig_path.read_text(
        encoding="utf-8"
    )

    assert [call["locale"] for call in launched] == ["en-US", "zh-CN"]
    assert all(call["geoip"] is True for call in launched)
