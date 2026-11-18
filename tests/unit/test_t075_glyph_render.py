"""t075 AC-007: real glyph rasterization proof (FreeType, ctypes).

fc-list language enumeration is not rendering: a font can report
``zh`` coverage while every CJK codepoint shapes to the ``.notdef``
box.  These tests rasterize real glyphs and prove the probe
discriminates — a real CJK face renders 中/文/字 as distinct,
inked glyphs, while a Latin-only font maps the same codepoints to
glyph 0 with a bitmap identical to its own ``.notdef``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cbrowser.runtime_agent.glyph_render import (
    GlyphRenderError,
    GlyphRenderUnavailable,
    prove_cjk_render,
    render_codepoint,
)

CJK_FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
LATIN_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _freetype_available() -> bool:
    import ctypes.util

    return ctypes.util.find_library("freetype") is not None


needs_real_render = pytest.mark.skipif(
    not _freetype_available()
    or not CJK_FONT.is_file()
    or not LATIN_FONT.is_file(),
    reason="FreeType or fixture fonts unavailable",
)


@needs_real_render
def test_cjk_font_renders_real_glyphs() -> None:
    """中/文/字 each map to a distinct, inked, non-.notdef glyph."""
    _, notdef_bitmap = render_codepoint(CJK_FONT, 0)
    assert notdef_bitmap  # the .notdef box itself has ink
    seen: set[bytes] = set()
    for codepoint in (0x4E2D, 0x6587, 0x5B57):
        glyph_index, bitmap = render_codepoint(CJK_FONT, codepoint)
        assert glyph_index != 0, hex(codepoint)
        assert any(bitmap), hex(codepoint)
        assert bitmap != notdef_bitmap, hex(codepoint)
        seen.add(bitmap)
    # Three different ideographs must not collapse to one bitmap.
    assert len(seen) == 3


@needs_real_render
def test_prove_cjk_render_accepts_real_cjk_font() -> None:
    assert prove_cjk_render(CJK_FONT) is True


@needs_real_render
def test_prove_cjk_render_rejects_latin_only_font() -> None:
    """DejaVu maps 中 to glyph 0 — tofu — so the proof refuses it."""
    glyph_index, bitmap = render_codepoint(LATIN_FONT, 0x4E2D)
    assert glyph_index == 0
    _, notdef_bitmap = render_codepoint(LATIN_FONT, 0)
    assert bitmap == notdef_bitmap
    assert prove_cjk_render(LATIN_FONT) is False


@needs_real_render
def test_prove_cjk_render_accepts_latin_glyphs_from_latin_font() -> None:
    glyph_index, bitmap = render_codepoint(LATIN_FONT, 0x41)
    assert glyph_index != 0
    assert any(bitmap)


@needs_real_render
def test_unreadable_font_raises_instead_of_passing(tmp_path: Path) -> None:
    junk = tmp_path / "junk.ttf"
    junk.write_bytes(b"not a font at all")
    with pytest.raises(GlyphRenderError):
        prove_cjk_render(junk)


def test_missing_freetype_is_unavailable(monkeypatch) -> None:
    """Without the library the probe reports unavailable, never a pass."""
    import cbrowser.runtime_agent.glyph_render as module

    monkeypatch.setattr(module.ctypes.util, "find_library", lambda _name: None)
    monkeypatch.setattr(module.ctypes, "CDLL", lambda _name: (_ for _ in ()).throw(OSError("no such library")))
    with pytest.raises(GlyphRenderUnavailable):
        render_codepoint(LATIN_FONT, 0x41)


@needs_real_render
def test_render_is_deterministic() -> None:
    first = render_codepoint(CJK_FONT, 0x4E2D)
    second = render_codepoint(CJK_FONT, 0x4E2D)
    assert first == second
