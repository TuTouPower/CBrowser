"""Runtime Agent preview capture loop (t040)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

from cbrowser.preview import (
    CAPTURE_INTERVAL_SEC,
    PreviewMeta,
    PreviewPolicy,
    capture_screenshot_params,
    commit_preview,
    read_policy,
)
from cbrowser.runtime_agent.protocol import utc_now_iso

logger = logging.getLogger("cbrowser.runtime_agent.preview_capture")

PREVIEW_MOUNT_DIR = Path("/data/preview")

CdpSend = Callable[[str, dict[str, Any], str | None], Awaitable[dict[str, Any]]]


def cdp_send_from_proxy(cdp_proxy: Any) -> CdpSend:
    async def send(
        method: str, params: dict[str, Any], session: str | None = None
    ) -> dict[str, Any]:
        if not cdp_proxy.agent_ws or cdp_proxy.shutting_down:
            raise RuntimeError("CDP proxy is not connected")
        async with cdp_proxy._lock:
            cid = cdp_proxy._allocate_cmd_id()
        req: dict[str, Any] = {"id": cid, "method": method, "params": params or {}}
        if session is not None:
            req["sessionId"] = session
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        cdp_proxy.pending_cmd_futures[cid] = fut
        try:
            await cdp_proxy.agent_ws.send(json.dumps(req))
            resp = await asyncio.wait_for(fut, timeout=5.0)
        finally:
            cdp_proxy.pending_cmd_futures.pop(cid, None)
            if not fut.done():
                fut.cancel()
        if "error" in resp or "result" not in resp:
            raise RuntimeError("CDP command was not acknowledged")
        return resp["result"]

    return send


class PreviewCaptureLoop:
    def __init__(
        self, data_root: Path | str, cdp_send: CdpSend, instance_id: str
    ) -> None:
        self.directory = Path(data_root)
        self.cdp_send = cdp_send
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
        policy = self._policy or read_policy(self.directory)
        if policy is None or not policy.enabled or policy.runtime_instance_id is None:
            return

        targets = await self.cdp_send("Target.getTargets", {}, None)
        page = next(
            (
                t
                for t in targets.get("targetInfos", [])
                if t.get("type") == "page"
            ),
            None,
        )
        if page is None:
            return
        target_id = page.get("targetId")
        if not isinstance(target_id, str) or not target_id:
            return
        attached = await self.cdp_send(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
            None,
        )
        session = attached.get("sessionId")
        if not isinstance(session, str) or not session:
            return
        try:
            metrics = await self.cdp_send("Page.getLayoutMetrics", {}, session)
            viewport = (
                metrics.get("cssLayoutViewport")
                or metrics.get("layoutViewport")
                or {}
            )
            vw = int(viewport.get("clientWidth", 0) or 0)
            vh = int(viewport.get("clientHeight", 0) or 0)
            if vw <= 0 or vh <= 0:
                return
            shot = await self.cdp_send(
                "Page.captureScreenshot",
                capture_screenshot_params(vw, vh),
                session,
            )
            jpeg = base64.b64decode(shot["data"])
            meta = PreviewMeta(
                captured_at=utc_now_iso(),
                runtime_instance_id=policy.runtime_instance_id,
                policy_epoch=policy.epoch,
            )
            if commit_preview(self.directory, jpeg, meta, policy):
                self.last_captured_at = meta.captured_at
        finally:
            try:
                await self.cdp_send(
                    "Target.detachFromTarget",
                    {"sessionId": session},
                    None,
                )
            except Exception as exc:
                logger.warning(
                    "Preview detach failed: error_type=%s", type(exc).__name__
                )

    async def run(self) -> None:
        while True:
            try:
                await self.capture_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.error_count += 1
                logger.debug(
                    "Preview capture failed: error_type=%s failures=%d",
                    type(exc).__name__,
                    self.error_count,
                )
            try:
                await asyncio.wait_for(
                    self._wake.wait(), timeout=CAPTURE_INTERVAL_SEC
                )
                self._wake.clear()
            except asyncio.TimeoutError:
                pass
