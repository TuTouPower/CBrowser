"""Profile preview policy, storage and freshness rules (t040).

Single source of truth shared by the API, Supervisor and Runtime Agent.
Screenshots are Cookie-grade private data: this module only carries bytes and
metadata, never logs paths or contents.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cbrowser.shared.atomic_write import atomic_write_bytes
from pydantic import BaseModel, Field

PREVIEW_WIDTH = 480
JPEG_QUALITY = 70
CAPTURE_INTERVAL_SEC = 15.0

POLICY_FILE = "policy.json"
META_FILE = "meta.json"
FRAME_RETENTION_SEC = 60.0


class PreviewPolicy(BaseModel):
    enabled: bool
    epoch: int
    runtime_instance_id: str | None = None


class PreviewMeta(BaseModel):
    captured_at: str
    runtime_instance_id: str
    policy_epoch: int
    image_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


def frame_path(directory: Path, meta: PreviewMeta) -> Path:
    if meta.image_sha256 is None:
        raise ValueError("Preview metadata has no committed frame")
    timestamp_key = hashlib.sha256(meta.captured_at.encode()).hexdigest()
    return directory / f"frame_{timestamp_key}_{meta.image_sha256}.jpg"


def preview_dir(data_root: Path | str, profile_id: str) -> Path:
    return Path(data_root) / "profiles" / profile_id / "preview"


def _atomic_write(
    path: Path, payload: str | bytes, *, uid: int | None = None, gid: int | None = None
) -> None:
    # The write mechanism itself is the shared atomic-write primitive
    # (t062); this wrapper only adds the preview store's directory
    # creation and str/bytes payload handling.
    path.parent.mkdir(parents=True, exist_ok=True)
    data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    atomic_write_bytes(path, data, mode=0o600, uid=uid, gid=gid)


def read_policy(directory: Path) -> PreviewPolicy | None:
    path = directory / POLICY_FILE
    if not path.is_file():
        return None
    try:
        return PreviewPolicy.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError, OSError:
        return None


def write_policy(
    directory: Path,
    policy: PreviewPolicy,
    *,
    uid: int | None = None,
    gid: int | None = None,
) -> None:
    _atomic_write(directory / POLICY_FILE, policy.model_dump_json(), uid=uid, gid=gid)


def read_meta(directory: Path) -> PreviewMeta | None:
    path = directory / META_FILE
    if not path.is_file():
        return None
    try:
        return PreviewMeta.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError, OSError:
        return None


def _remove(directory: Path, name: str) -> None:
    try:
        (directory / name).unlink(missing_ok=True)
    except OSError:
        pass


@contextmanager
def _preview_lock(directory: Path) -> Iterator[None]:
    # Lock the directory inode: no root-owned lock file can prevent the
    # Browser's UID from participating. Production writers share Linux.
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def clear_preview(directory: Path) -> None:
    try:
        with _preview_lock(directory):
            _remove(directory, META_FILE)
            for path in directory.glob("*.jpg"):
                _remove(directory, path.name)
    except FileNotFoundError:
        pass


def _selected_frame(directory: Path) -> Path | None:
    meta = read_meta(directory)
    return frame_path(directory, meta) if meta and meta.image_sha256 else None


def _collect_expired_frames(directory: Path) -> None:
    selected = _selected_frame(directory)
    cutoff = time.time() - FRAME_RETENTION_SEC
    for path in directory.glob("*.jpg"):
        try:
            if path != selected and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def _policy_matches(
    current: PreviewPolicy | None, expected: PreviewPolicy, meta: PreviewMeta
) -> bool:
    return (
        current is not None
        and current.enabled
        and current.epoch == expected.epoch
        and current.runtime_instance_id == expected.runtime_instance_id
        and meta.policy_epoch == expected.epoch
        and meta.runtime_instance_id == expected.runtime_instance_id
    )


def commit_preview(
    directory: Path,
    jpeg: bytes,
    meta: PreviewMeta,
    policy: PreviewPolicy,
) -> bool:
    """Write a captured frame only when the live policy still authorises it.

    A policy revocation, epoch bump or instance change that lands while a
    screenshot is in flight discards the frame and removes any residue.
    """
    if not directory.is_dir():
        return False
    with _preview_lock(directory):
        if not _policy_matches(read_policy(directory), policy, meta):
            return False
        meta.image_sha256 = hashlib.sha256(jpeg).hexdigest()
        image = frame_path(directory, meta)
        published = False
        try:
            _atomic_write(image, jpeg)
            if not _policy_matches(read_policy(directory), policy, meta):
                return False
            _atomic_write(directory / META_FILE, meta.model_dump_json())
            published = True
            return True
        finally:
            # A duplicate capture may already name the selected frame.
            # Never delete that published snapshot when metadata fails.
            if not published and _selected_frame(directory) != image:
                _remove(directory, image.name)
            _collect_expired_frames(directory)


def read_preview(
    directory: Path,
    policy: PreviewPolicy,
    *,
    epoch: int,
    runtime_instance_id: str | None,
) -> tuple[PreviewMeta, bytes] | None:
    """Open the metadata-selected frame once and return that exact snapshot."""
    meta = read_meta(directory)
    if meta is None or meta.image_sha256 is None:
        return None
    instance = runtime_instance_id or meta.runtime_instance_id
    if not (
        policy.enabled
        and policy.epoch == epoch
        and meta.policy_epoch == epoch
        and meta.runtime_instance_id == instance
        and (
            policy.runtime_instance_id is None or policy.runtime_instance_id == instance
        )
    ):
        return None
    try:
        with frame_path(directory, meta).open("rb") as stream:
            data = stream.read()
    except OSError:
        return None
    if hashlib.sha256(data).hexdigest() != meta.image_sha256:
        return None
    return meta, data
