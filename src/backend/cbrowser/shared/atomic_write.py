"""The one atomic file-write implementation (t062).

Mechanism: write to a uniquely named temporary file in the target
directory (``O_EXCL``, so a sandbox-created symlink is never followed),
flush + fsync, set the final mode (and optionally ownership), then
``os.replace`` onto the target and fsync the directory so the rename
itself is durable. A failure at any step leaves the previous file
untouched and removes the temporary file.

Streaming writers that cannot hold their payload in memory (the
artifact store upload path) follow the same durability contract —
flush + fsync + ``os.replace`` + directory fsync — at their call site;
every whole-payload write goes through this module.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    mode: int = 0o600,
    uid: int | None = None,
    gid: int | None = None,
) -> None:
    temporary = path.parent / (uuid.uuid4().hex + ".tmp")
    owned = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        owned = True
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fchmod(output.fileno(), mode)
            if uid is not None or gid is not None:
                os.fchown(
                    output.fileno(),
                    uid if uid is not None else -1,
                    gid if gid is not None else -1,
                )
            os.fsync(output.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        # Only ever remove a staging file this call created: if the
        # exclusive open collided, the file at that path belongs to
        # another writer and must survive.
        if owned:
            temporary.unlink(missing_ok=True)


def atomic_write_text(
    path: Path,
    text: str,
    *,
    mode: int = 0o600,
    uid: int | None = None,
    gid: int | None = None,
    encoding: str = "utf-8",
) -> None:
    atomic_write_bytes(
        path, text.encode(encoding), mode=mode, uid=uid, gid=gid
    )
