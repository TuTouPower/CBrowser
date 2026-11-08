"""Single reader for internal credential files with strict mode checks."""

from __future__ import annotations

import os
import stat
from pathlib import Path

_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NONBLOCK", 0)
)
_READ_CHUNK = 65536
_MAX_SECRET_BYTES = 1 << 20


def read_secret_file(
    path: Path | str,
    *,
    label: str = "Secret file",
    minimum_bytes: int = 32,
) -> str:
    """Read a private credential file; group/other access is rejected."""
    try:
        fd = os.open(path, _OPEN_FLAGS)
    except OSError:
        raise RuntimeError(f"Cannot read {label}") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f"Cannot read {label}")
        if info.st_mode & 0o077:
            raise RuntimeError(
                f"{label} must not be readable by group or others"
            )
        data = bytearray()
        while True:
            chunk = os.read(fd, _READ_CHUNK)
            if not chunk:
                break
            if len(data) + len(chunk) > _MAX_SECRET_BYTES:
                raise RuntimeError(f"Cannot read {label}")
            data.extend(chunk)
        try:
            value = bytes(data).decode("utf-8").strip()
        except UnicodeError:
            raise RuntimeError(f"Cannot read {label}") from None
        if len(value.encode("utf-8")) < minimum_bytes:
            raise RuntimeError(
                f"{label} must contain at least {minimum_bytes} bytes"
            )
        return value
    except OSError:
        raise RuntimeError(f"Cannot read {label}") from None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
