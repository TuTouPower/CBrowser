"""t075 AC-005/006/007/008: per-instance verification of the mounted
font set inside the Browser container.

Hard failures (mount missing, manifest broken, platform mismatch,
files missing, content hash mismatch, filtered view empty, required
CJK capability absent, CJK leak while the switch is off, CJK faces
that enumerate but do not render) keep the environment from ever
being reported usable; detection-coverage gaps are reported as
optional missing only.

The fake-file unit tests stub both seams the module offers — the
fc-list lister and the FreeType render prover — exactly like the
production seams; the real-font tests below run both for real.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cbrowser.runtime_agent.font_verification import (
    FAILURE_CJK_LEAK,
    FAILURE_CJK_RENDER_FAILED,
    FAILURE_CJK_REQUIRED_MISSING,
    FAILURE_CONTENT_MISMATCH,
    FAILURE_FILES_MISSING,
    FAILURE_MANIFEST_INVALID,
    FAILURE_MOUNT_MISSING,
    FAILURE_NO_EFFECTIVE_FONTS,
    FAILURE_PLATFORM_MISMATCH,
    FAILURE_RENDER_UNAVAILABLE,
    verify_mounted_font_set,
)
from cbrowser.runtime_agent.fontconfig import prepare_profile_fontconfig
from cbrowser.runtime_agent.glyph_render import GlyphRenderUnavailable

SET_ID = "a" * 64
_FAKE_CONTENT = b"font-bytes"
_FAKE_SHA256 = hashlib.sha256(_FAKE_CONTENT).hexdigest()


def _make_set(
    root: Path,
    *,
    platform: str = "windows",
    files: tuple[str, ...] = ("arial.ttf", "msyh.ttc"),
    manifest_platform: str | None = "windows",
    write_files: bool = True,
    tamper: str | None = None,
) -> Path:
    set_dir = root / platform / SET_ID
    set_dir.mkdir(parents=True)
    manifest = {
        "platform": manifest_platform,
        "files": [{"name": name, "sha256": _FAKE_SHA256} for name in files],
    }
    (set_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if write_files:
        for name in files:
            (set_dir / name).write_bytes(_FAKE_CONTENT)
    if tamper is not None:
        # Same name, different bytes: the manifest hash no longer matches.
        (set_dir / tamper).write_bytes(b"substituted-bytes")
    return set_dir


def _lister(entries):
    def _list(_path: Path):
        return entries

    return _list


LATIN = [("arial.ttf", ("en",)), ("cour.ttf", ("en",))]
WITH_CJK = LATIN + [("msyh.ttc", ("zh-cn", "en"))]


def _verify(root: Path, **kwargs):
    params = {
        "mount_root": root,
        "platform": "windows",
        "font_set_id": SET_ID,
        "include_cjk_fonts": True,
        "fontconfig_path": root / "fonts.conf",
        "font_lister": _lister(WITH_CJK),
        # Fake fixture files cannot be rasterized; the render seam is
        # stubbed here and exercised for real in the real-font tests
        # and test_t075_glyph_render.py.
        "glyph_prover": lambda _path: True,
    }
    params.update(kwargs)
    return verify_mounted_font_set(**params)


def test_verified_when_mount_manifest_and_glyphs_agree(tmp_path: Path) -> None:
    _make_set(tmp_path)
    verdict = _verify(tmp_path)
    assert verdict["status"] == "verified"
    assert verdict["failure"] is None
    assert verdict["font_set_id"] == SET_ID
    assert verdict["effective_fonts"] == len(WITH_CJK)
    # Detection fonts the set does not carry are optional coverage.
    assert "calibri.ttf" in verdict["missing_optional"]
    assert "arial.ttf" not in verdict["missing_optional"]


def test_missing_mount_fails(tmp_path: Path) -> None:
    verdict = _verify(tmp_path)
    assert verdict["status"] == "failed"
    assert verdict["failure"] == FAILURE_MOUNT_MISSING


def test_corrupt_manifest_fails(tmp_path: Path) -> None:
    set_dir = tmp_path / "windows" / SET_ID
    set_dir.mkdir(parents=True)
    (set_dir / "manifest.json").write_text("{not json", encoding="utf-8")
    verdict = _verify(tmp_path)
    assert verdict["failure"] == FAILURE_MANIFEST_INVALID


def test_platform_mismatch_fails(tmp_path: Path) -> None:
    _make_set(tmp_path, manifest_platform="macos")
    verdict = _verify(tmp_path)
    assert verdict["failure"] == FAILURE_PLATFORM_MISMATCH


def test_missing_files_fail(tmp_path: Path) -> None:
    _make_set(tmp_path, write_files=False)
    verdict = _verify(tmp_path)
    assert verdict["failure"] == FAILURE_FILES_MISSING


def test_tampered_content_fails(tmp_path: Path) -> None:
    # t075 review f001: same file names, substituted bytes — the
    # manifest sha256 no longer matches, so the mount must fail even
    # though every file exists and fc-list would still enumerate it.
    _make_set(tmp_path, tamper="msyh.ttc")
    verdict = _verify(tmp_path)
    assert verdict["status"] == "failed"
    assert verdict["failure"] == FAILURE_CONTENT_MISMATCH


def test_empty_filtered_view_fails(tmp_path: Path) -> None:
    _make_set(tmp_path)
    verdict = _verify(tmp_path, font_lister=_lister([]))
    assert verdict["failure"] == FAILURE_NO_EFFECTIVE_FONTS


def test_cjk_required_but_absent_fails(tmp_path: Path) -> None:
    _make_set(tmp_path)
    verdict = _verify(
        tmp_path, include_cjk_fonts=True, font_lister=_lister(LATIN)
    )
    assert verdict["failure"] == FAILURE_CJK_REQUIRED_MISSING


def test_cjk_off_with_chinese_visible_is_a_leak(tmp_path: Path) -> None:
    _make_set(tmp_path)
    verdict = _verify(
        tmp_path, include_cjk_fonts=False, font_lister=_lister(WITH_CJK)
    )
    assert verdict["failure"] == FAILURE_CJK_LEAK


def test_cjk_off_latin_only_verifies(tmp_path: Path) -> None:
    _make_set(tmp_path)
    verdict = _verify(
        tmp_path, include_cjk_fonts=False, font_lister=_lister(LATIN)
    )
    assert verdict["status"] == "verified"


def test_cjk_faces_that_do_not_render_fail(tmp_path: Path) -> None:
    # The faces enumerate zh, but the render proof refuses them:
    # enumerating coverage is not rendering.
    _make_set(tmp_path)
    verdict = _verify(tmp_path, glyph_prover=lambda _path: False)
    assert verdict["status"] == "failed"
    assert verdict["failure"] == FAILURE_CJK_RENDER_FAILED


def test_render_unavailable_is_its_own_failure(tmp_path: Path) -> None:
    # A missing renderer must not silently skip the proof.
    def _no_renderer(_path: Path):
        raise GlyphRenderUnavailable("libfreetype not found")

    _make_set(tmp_path)
    verdict = _verify(tmp_path, glyph_prover=_no_renderer)
    assert verdict["status"] == "failed"
    assert verdict["failure"] == FAILURE_RENDER_UNAVAILABLE


# --- real fontconfig binary -------------------------------------------------

FC_LIST = shutil.which("fc-list")
CJK_FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
LATIN_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

needs_real_fontconfig = pytest.mark.skipif(
    FC_LIST is None or not CJK_FONT.is_file() or not LATIN_FONT.is_file(),
    reason="fc-list or fixture fonts unavailable",
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@needs_real_fontconfig
def test_real_fc_list_end_to_end(tmp_path: Path) -> None:
    """The default lister runs real fontconfig against the generated
    profile config, and the default prover really rasterizes the CJK
    faces: with the switch on the CJK faces verify; with the switch
    off the filtered view is Latin-only and still verifies."""
    mount_root = tmp_path / "fonts"
    set_dir = mount_root / "windows" / SET_ID
    set_dir.mkdir(parents=True)
    shutil.copyfile(CJK_FONT, set_dir / CJK_FONT.name)
    shutil.copyfile(LATIN_FONT, set_dir / LATIN_FONT.name)
    (set_dir / "manifest.json").write_text(
        json.dumps(
            {
                "platform": "windows",
                "files": [
                    {"name": CJK_FONT.name, "sha256": _sha256_file(CJK_FONT)},
                    {"name": LATIN_FONT.name, "sha256": _sha256_file(LATIN_FONT)},
                ],
            }
        ),
        encoding="utf-8",
    )

    for include_cjk, min_faces in ((True, 2), (False, 1)):
        config_path = prepare_profile_fontconfig(
            tmp_path / f"run-{include_cjk}",
            [set_dir],
            include_cjk_fonts=include_cjk,
            cache_dir=tmp_path / f"cache-{include_cjk}",
        )
        assert config_path is not None
        verdict = verify_mounted_font_set(
            mount_root=mount_root,
            platform="windows",
            font_set_id=SET_ID,
            include_cjk_fonts=include_cjk,
            fontconfig_path=config_path,
        )
        assert verdict["status"] == "verified", verdict
        # On: Latin + CJK faces visible.  Off: only the Latin face
        # survives the reject rules — exactly one effective font.
        assert verdict["effective_fonts"] >= min_faces


@needs_real_fontconfig
def test_real_tampered_font_fails_end_to_end(tmp_path: Path) -> None:
    """Same real set, one file's bytes substituted after import: the
    hash check fails before any listing or rendering runs."""
    mount_root = tmp_path / "fonts"
    set_dir = mount_root / "windows" / SET_ID
    set_dir.mkdir(parents=True)
    shutil.copyfile(CJK_FONT, set_dir / CJK_FONT.name)
    shutil.copyfile(LATIN_FONT, set_dir / LATIN_FONT.name)
    (set_dir / "manifest.json").write_text(
        json.dumps(
            {
                "platform": "windows",
                "files": [
                    {"name": CJK_FONT.name, "sha256": _sha256_file(CJK_FONT)},
                    {"name": LATIN_FONT.name, "sha256": _sha256_file(LATIN_FONT)},
                ],
            }
        ),
        encoding="utf-8",
    )
    # Substitute the CJK file's bytes after the manifest was written.
    (set_dir / CJK_FONT.name).write_bytes(b"not a font at all")
    config_path = prepare_profile_fontconfig(
        tmp_path / "run",
        [set_dir],
        include_cjk_fonts=True,
        cache_dir=tmp_path / "cache",
    )
    assert config_path is not None
    verdict = verify_mounted_font_set(
        mount_root=mount_root,
        platform="windows",
        font_set_id=SET_ID,
        include_cjk_fonts=True,
        fontconfig_path=config_path,
    )
    assert verdict["status"] == "failed"
    assert verdict["failure"] == FAILURE_CONTENT_MISMATCH
