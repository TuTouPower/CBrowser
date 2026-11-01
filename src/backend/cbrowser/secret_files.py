"""Single reader for internal credential files with strict mode checks."""

from __future__ import annotations

from pathlib import Path


def read_secret_file(
    path: Path | str,
    *,
    label: str = "Secret file",
    minimum_bytes: int = 32,
) -> str:
    """Read a private credential file; group/other access is rejected."""
    target = Path(path)
    try:
        stat = target.stat()
    except OSError:
        raise RuntimeError(f"Cannot read {label}") from None
    if stat.st_mode & 0o077:
        raise RuntimeError(f"{label} must not be readable by group or others")
    try:
        value = target.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise RuntimeError(f"Cannot read {label}") from None
    if len(value.encode("utf-8")) < minimum_bytes:
        raise RuntimeError(f"{label} must contain at least {minimum_bytes} bytes")
    return value
