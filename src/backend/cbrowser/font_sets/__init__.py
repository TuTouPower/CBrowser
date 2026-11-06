"""Content-addressed platform font set storage and verification."""

from .manifest import (
    DETECTION_FONTS,
    FONT_EXTENSIONS,
    check_font_set,
    compute_set_id,
    default_font_set,
    discover_font_files,
    get_font_set,
    import_font_set,
    list_font_sets,
)

__all__ = [
    "DETECTION_FONTS",
    "FONT_EXTENSIONS",
    "check_font_set",
    "compute_set_id",
    "default_font_set",
    "discover_font_files",
    "get_font_set",
    "import_font_set",
    "list_font_sets",
]
