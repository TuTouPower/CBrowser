"""Replace controller files durably without following a sandbox-created symlink."""

import os
import uuid
from pathlib import Path


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    temporary = path.parent / (uuid.uuid4().hex + ".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fchmod(output.fileno(), mode)
            os.fsync(output.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
