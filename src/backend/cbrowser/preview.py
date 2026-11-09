"""Profile preview policy, storage and freshness rules (t040).

Single source of truth shared by the API, Supervisor and Runtime Agent.
Screenshots are Cookie-grade private data: this module only carries bytes and
metadata, never logs paths or contents.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

PREVIEW_WIDTH = 480
JPEG_QUALITY = 70
CAPTURE_INTERVAL_SEC = 15.0

POLICY_FILE = "policy.json"
IMAGE_FILE = "latest.jpg"
META_FILE = "meta.json"


class PreviewPolicy(BaseModel):
    enabled: bool
    epoch: int
    runtime_instance_id: str | None = None


class PreviewMeta(BaseModel):
    captured_at: str
    runtime_instance_id: str
    policy_epoch: int


def preview_dir(data_root: Path | str, profile_id: str) -> Path:
    return Path(data_root) / "profiles" / profile_id / "preview"


def _atomic_write(
    path: Path, payload: str | bytes, *, uid: int | None = None, gid: int | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        if isinstance(payload, bytes):
            tmp.write_bytes(payload)
        else:
            tmp.write_text(payload, encoding="utf-8")
        os.chmod(tmp, 0o600)
        if uid is not None or gid is not None:
            os.chown(
                tmp,
                uid if uid is not None else -1,
                gid if gid is not None else -1,
            )
        os.replace(tmp, path)
    except BaseException:
        # Never leave a half-written staging file behind (cancellation,
        # disk errors); a stale tmp could otherwise be mistaken for a
        # pending write by later readers.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def read_policy(directory: Path) -> PreviewPolicy | None:
    path = directory / POLICY_FILE
    if not path.is_file():
        return None
    try:
        return PreviewPolicy.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def write_policy(
    directory: Path, policy: PreviewPolicy, *, uid: int | None = None, gid: int | None = None
) -> None:
    _atomic_write(directory / POLICY_FILE, policy.model_dump_json(), uid=uid, gid=gid)


def read_meta(directory: Path) -> PreviewMeta | None:
    path = directory / META_FILE
    if not path.is_file():
        return None
    try:
        return PreviewMeta.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _remove(directory: Path, name: str) -> None:
    try:
        (directory / name).unlink(missing_ok=True)
    except OSError:
        pass


def clear_preview(directory: Path) -> None:
    _remove(directory, IMAGE_FILE)
    _remove(directory, META_FILE)


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
    current = read_policy(directory)
    if not _policy_matches(current, policy, meta):
        clear_preview(directory)
        return False
    _atomic_write(directory / IMAGE_FILE, jpeg)
    _atomic_write(directory / META_FILE, meta.model_dump_json())
    return True


def is_current_preview(
    directory: Path,
    policy: PreviewPolicy,
    *,
    epoch: int,
    runtime_instance_id: str | None,
) -> bool:
    meta = read_meta(directory)
    if meta is None or not (directory / IMAGE_FILE).is_file():
        return False
    return (
        policy.enabled
        and policy.epoch == epoch
        and meta.policy_epoch == epoch
        and meta.runtime_instance_id == runtime_instance_id
        and (
            policy.runtime_instance_id is None
            or policy.runtime_instance_id == runtime_instance_id
        )
    )


def capture_screenshot_params(
    viewport_width: int, viewport_height: int
) -> dict[str, Any]:
    """CDP Page.captureScreenshot params: viewport only, scaled to 480px.

    Uses clip.scale instead of Emulation.setDeviceMetricsOverride so the page
    layout, visibility and focus are untouched (AC-007).
    """
    return {
        "format": "jpeg",
        "quality": JPEG_QUALITY,
        "clip": {
            "x": 0,
            "y": 0,
            "width": viewport_width,
            "height": viewport_height,
            "scale": PREVIEW_WIDTH / viewport_width,
        },
    }
