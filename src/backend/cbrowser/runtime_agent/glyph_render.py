"""Real glyph rasterization proof, via FreeType (ctypes, no new dependency).

t075 AC-007: claiming "real platform Chinese renders correctly" needs
more than an fc-list language enumeration — a corrupt or unshaped font
can report ``zh`` coverage while every CJK codepoint falls back to the
``.notdef`` box.  This module rasterizes a few CJK codepoints with the
system FreeType (the same library fontconfig itself links) and proves
each one is a *real* glyph: it maps to a non-zero glyph index, its
bitmap carries ink, and its bitmap differs from the font's own
``.notdef`` bitmap.  A Latin-only font maps the same codepoints to
glyph 0 with a bitmap identical to ``.notdef`` — the probe
discriminates, it does not merely count non-zero pixels.

Only the stable C entry points are used; the ``FT_FaceRec`` /
``FT_GlyphSlotRec`` layouts are pinned to the FreeType 2 ABI
(``glyph`` sits between ``underline_thickness`` and ``size``;
``FT_BBox`` is four ``FT_Pos`` longs).  Any layout surprise surfaces
as a sanity failure (family name / units-per-EM unreadable), never as
a silent pass.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
from pathlib import Path

# Codepoints the CJK proof renders: 中 文 字 — three distinct,
# common CJK ideographs a real platform Chinese font must carry.
CJK_PROOF_CODEPOINTS: tuple[int, ...] = (0x4E2D, 0x6587, 0x5B57)

_PIXEL_SIZE = 32
_FT_LOAD_RENDER = 0x4


class GlyphRenderError(Exception):
    """The font file could not be opened or a glyph could not be rendered."""


class GlyphRenderUnavailable(Exception):
    """FreeType itself is unavailable in this environment."""


class _Bitmap(ctypes.Structure):
    _fields_ = [
        ("rows", ctypes.c_uint),
        ("width", ctypes.c_uint),
        ("pitch", ctypes.c_int),
        ("buffer", ctypes.c_void_p),
        ("num_grays", ctypes.c_ushort),
        ("pixel_mode", ctypes.c_ubyte),
        ("palette_mode", ctypes.c_ubyte),
        ("palette", ctypes.c_void_p),
    ]


class _GlyphSlot(ctypes.Structure):
    _fields_ = [
        ("library", ctypes.c_void_p),
        ("face", ctypes.c_void_p),
        ("next", ctypes.c_void_p),
        ("reserved", ctypes.c_uint),
        ("generic", ctypes.c_void_p * 2),
        ("metrics", ctypes.c_long * 8),
        ("linearHoriAdvance", ctypes.c_long),
        ("linearVertAdvance", ctypes.c_long),
        ("advance", ctypes.c_long * 2),
        ("format", ctypes.c_uint),
        ("bitmap", _Bitmap),
        ("bitmap_left", ctypes.c_int),
        ("bitmap_top", ctypes.c_int),
    ]


class _Face(ctypes.Structure):
    # Field order follows freetype.h FT_FaceRec: glyph comes right
    # after underline_thickness, before size.
    _fields_ = [
        ("num_faces", ctypes.c_long),
        ("face_index", ctypes.c_long),
        ("face_flags", ctypes.c_long),
        ("style_flags", ctypes.c_long),
        ("num_glyphs", ctypes.c_long),
        ("family_name", ctypes.c_char_p),
        ("style_name", ctypes.c_char_p),
        ("num_fixed_sizes", ctypes.c_int),
        ("available_sizes", ctypes.c_void_p),
        ("num_charmaps", ctypes.c_int),
        ("charmaps", ctypes.c_void_p),
        ("generic", ctypes.c_void_p * 2),
        ("bbox", ctypes.c_long * 4),
        ("units_per_EM", ctypes.c_ushort),
        ("ascender", ctypes.c_short),
        ("descender", ctypes.c_short),
        ("height", ctypes.c_short),
        ("max_advance_width", ctypes.c_short),
        ("max_advance_height", ctypes.c_short),
        ("underline_position", ctypes.c_short),
        ("underline_thickness", ctypes.c_short),
        ("glyph", ctypes.POINTER(_GlyphSlot)),
        ("size", ctypes.c_void_p),
        ("charmap", ctypes.c_void_p),
        ("driver", ctypes.c_void_p),
        ("memory", ctypes.c_void_p),
        ("stream", ctypes.c_void_p),
        ("sizes_list", ctypes.c_void_p * 2),
        ("autohint", ctypes.c_void_p),
        ("extensions", ctypes.c_void_p),
        ("internal", ctypes.c_void_p),
    ]


def _load_library():
    """Load libfreetype, or raise GlyphRenderUnavailable."""
    for candidate in (
        ctypes.util.find_library("freetype"),
        "libfreetype.so.6",
        "libfreetype.so",
    ):
        if not candidate:
            continue
        try:
            lib = ctypes.CDLL(candidate)
        except OSError:
            continue
        lib.FT_Init_FreeType.restype = ctypes.c_int
        lib.FT_Init_FreeType.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        lib.FT_New_Face.restype = ctypes.c_int
        lib.FT_New_Face.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_long,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        lib.FT_Set_Pixel_Sizes.restype = ctypes.c_int
        lib.FT_Set_Pixel_Sizes.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        lib.FT_Get_Char_Index.restype = ctypes.c_uint
        lib.FT_Get_Char_Index.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.FT_Load_Glyph.restype = ctypes.c_int
        lib.FT_Load_Glyph.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_int32,
        ]
        lib.FT_Done_Face.restype = ctypes.c_int
        lib.FT_Done_Face.argtypes = [ctypes.c_void_p]
        lib.FT_Done_FreeType.restype = ctypes.c_int
        lib.FT_Done_FreeType.argtypes = [ctypes.c_void_p]
        return lib
    raise GlyphRenderUnavailable("libfreetype not found")


def render_codepoint(
    font_path: Path, codepoint: int, pixel_size: int = _PIXEL_SIZE
) -> tuple[int, bytes]:
    """Rasterize one codepoint; return ``(glyph_index, bitmap_bytes)``.

    The bitmap is the raw grayscale buffer (rows * abs(pitch) bytes).
    Raises :class:`GlyphRenderError` for an unusable font file and
    :class:`GlyphRenderUnavailable` when FreeType is missing.
    """
    lib = _load_library()
    library = ctypes.c_void_p()
    if lib.FT_Init_FreeType(ctypes.byref(library)) != 0:
        raise GlyphRenderError("FT_Init_FreeType failed")
    face_ptr = ctypes.c_void_p()
    try:
        if lib.FT_New_Face(library, str(font_path).encode(), 0, ctypes.byref(face_ptr)) != 0:
            raise GlyphRenderError(f"cannot open font face: {font_path}")
        face = ctypes.cast(face_ptr, ctypes.POINTER(_Face)).contents
        if not (0 < face.units_per_EM <= 16384):
            raise GlyphRenderError(
                f"implausible units_per_EM {face.units_per_EM} in {font_path}"
            )
        if lib.FT_Set_Pixel_Sizes(face_ptr, 0, pixel_size) != 0:
            raise GlyphRenderError(f"cannot set pixel size for {font_path}")
        glyph_index = lib.FT_Get_Char_Index(face_ptr, codepoint)
        if lib.FT_Load_Glyph(face_ptr, glyph_index, _FT_LOAD_RENDER) != 0:
            raise GlyphRenderError(
                f"cannot load glyph {glyph_index} from {font_path}"
            )
        slot = face.glyph.contents
        bitmap = slot.bitmap
        size = bitmap.rows * abs(bitmap.pitch)
        if size > 1_000_000:
            raise GlyphRenderError(
                f"implausible bitmap {bitmap.width}x{bitmap.rows} in {font_path}"
            )
        raw = (
            bytes((ctypes.c_ubyte * size).from_address(bitmap.buffer))
            if bitmap.buffer
            else b""
        )
        return glyph_index, raw
    finally:
        if face_ptr:
            lib.FT_Done_Face(face_ptr)
        lib.FT_Done_FreeType(library)


def prove_cjk_render(
    font_path: Path,
    codepoints: tuple[int, ...] = CJK_PROOF_CODEPOINTS,
) -> bool:
    """True only if every proof codepoint is a real, distinct glyph.

    A codepoint proves when it maps to a non-zero glyph index, its
    bitmap carries ink, and its bitmap differs from the font's own
    ``.notdef`` bitmap.  Returns False for a font that cannot render
    the codepoints (tofu) or whose outlines are empty; raises
    :class:`GlyphRenderError` for an unreadable font file.
    """
    _, notdef_bitmap = render_codepoint(font_path, 0)
    notdef_hash = hashlib.sha256(notdef_bitmap).hexdigest()
    for codepoint in codepoints:
        glyph_index, bitmap = render_codepoint(font_path, codepoint)
        if glyph_index == 0:
            return False
        if not any(bitmap):
            return False
        if hashlib.sha256(bitmap).hexdigest() == notdef_hash:
            return False
    return True
