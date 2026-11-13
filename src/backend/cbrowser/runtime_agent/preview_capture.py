"""Capture the Profile's isolated X11 display, including browser chrome."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from cbrowser.preview import (
    CAPTURE_INTERVAL_SEC,
    JPEG_QUALITY,
    PREVIEW_WIDTH,
    PreviewMeta,
    PreviewPolicy,
    commit_preview,
    read_policy,
)
from cbrowser.runtime_agent.protocol import utc_now_iso
from PIL import Image, ImageGrab

logger = logging.getLogger("cbrowser.runtime_agent.preview_capture")
PREVIEW_MOUNT_DIR = Path("/data/preview")
Capture = Callable[[str], tuple[bytes, tuple[int, int]]]


def capture_display(display: str) -> tuple[bytes, tuple[int, int]]:
    # Explicit X display disables Pillow's desktop-helper fallback. Never
    # allow an absent display to fall through to a macOS host screenshot.
    if not isinstance(display, str) or re.fullmatch(r":\d+(?:\.\d+)?", display) is None:
        raise ValueError("Preview requires an explicit local X11 display")
    if sys.platform != "linux":
        raise RuntimeError("Preview capture requires the isolated Linux display")
    with ImageGrab.grab(xdisplay=display) as image:
        size = (
            PREVIEW_WIDTH,
            max(1, round(image.height * PREVIEW_WIDTH / image.width)),
        )
        with (
            image.convert("RGB").resize(size, Image.Resampling.LANCZOS) as thumbnail,
            io.BytesIO() as output,
        ):
            thumbnail.save(output, "JPEG", quality=JPEG_QUALITY)
            return output.getvalue(), size


def valid_frame(jpeg: bytes, size: tuple[int, int]) -> bool:
    if size[0] != PREVIEW_WIDTH or size[1] <= 0 or not jpeg.endswith(b"\xff\xd9"):
        return False
    try:
        with Image.open(io.BytesIO(jpeg)) as image:
            if image.format != "JPEG" or image.size != size:
                return False
            image.load()
    except OSError, ValueError, Image.DecompressionBombError:
        return False
    try:
        checked = subprocess.run(
            ["jpeginfo", "--check", "-"],
            input=jpeg,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return False
    return checked.returncode == 0


class PreviewCaptureLoop:
    def __init__(
        self,
        data_root: Path | str,
        display: str,
        instance_id: str,
        *,
        capture: Capture = capture_display,
    ) -> None:
        self.directory = Path(data_root)
        self.display = display
        self.capture = capture
        self.instance_id = instance_id
        self._policy: PreviewPolicy | None = None
        self.last_captured_at: str | None = None
        self.error_count = 0
        self._wake = asyncio.Event()

    @property
    def policy(self) -> PreviewPolicy | None:
        return self._policy

    def set_policy(
        self,
        *,
        enabled: bool,
        epoch: int,
        runtime_instance_id: str | None,
    ) -> None:
        if self._policy is not None and epoch < self._policy.epoch:
            return
        self._policy = PreviewPolicy(
            enabled=enabled,
            epoch=epoch,
            runtime_instance_id=runtime_instance_id,
        )
        self._wake.set()

    async def capture_once(self) -> None:
        current = read_policy(self.directory)
        policy = self._policy or current
        if (
            policy is None
            or not policy.enabled
            or policy.runtime_instance_id != self.instance_id
            or current is None
            or not current.enabled
            or current.epoch != policy.epoch
            or current.runtime_instance_id != self.instance_id
        ):
            return
        jpeg, size = await asyncio.to_thread(self.capture, self.display)
        if not await asyncio.to_thread(valid_frame, jpeg, size):
            logger.warning("Preview frame rejected: error_type=invalid_jpeg")
            return
        meta = PreviewMeta(
            captured_at=utc_now_iso(),
            runtime_instance_id=self.instance_id,
            policy_epoch=policy.epoch,
        )
        if commit_preview(self.directory, jpeg, meta, policy):
            self.last_captured_at = meta.captured_at

    async def run(self) -> None:
        while True:
            try:
                await self.capture_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep the capture loop alive with redacted diagnostics
                self.error_count += 1
                logger.debug(
                    "Preview capture failed: error_type=%s failures=%d",
                    type(exc).__name__,
                    self.error_count,
                )
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=CAPTURE_INTERVAL_SEC)
                self._wake.clear()
            except TimeoutError:
                pass
