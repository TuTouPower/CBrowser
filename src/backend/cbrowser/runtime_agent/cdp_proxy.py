"""Chrome DevTools Protocol (CDP) client, proxy and download capture manager."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import websockets
from websockets.protocol import State

from .event_storage import EventStorage
from .protocol import DownloadEventRecord

logger = logging.getLogger("cbrowser.runtime_agent.cdp_proxy")


class CdpProxyManager:
    """Manages CDP loopback connection, download behavior rearm, and client proxying."""

    def __init__(
        self,
        browser_ws_url: str,
        default_download_dir: Path | str,
        profile_id: str,
        runtime_instance_id: str,
        event_storage: EventStorage,
    ) -> None:
        self.browser_ws_url = browser_ws_url
        self.default_download_dir = str(default_download_dir)
        self.profile_id = profile_id
        self.runtime_instance_id = runtime_instance_id
        self.event_storage = event_storage

        self.agent_ws: Any = None
        self._next_cmd_id = 10000
        self.pending_cmd_futures: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.active_downloads: dict[str, dict[str, Any]] = {}
        self.rearm_count = 0
        self.shutting_down = False
        self._event_listener_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def capture_alive(self) -> bool:
        """An open socket alone does not prove the event receiver is running."""
        return bool(
            not self.shutting_down
            and self.agent_ws is not None
            and self.agent_ws.state is State.OPEN
            and self._event_listener_task is not None
            and not self._event_listener_task.done()
        )

    async def start(self) -> None:
        """Connect to loopback Chrome CDP and arm default download capture."""
        Path(self.default_download_dir).mkdir(parents=True, exist_ok=True)
        self.agent_ws = await websockets.connect(
            self.browser_ws_url,
            max_size=32 * 1024 * 1024,
            ping_interval=10,
            ping_timeout=10,
        )
        self._event_listener_task = asyncio.create_task(self._listen_events())
        await self.rearm_download_capture()
        logger.info("CDP proxy manager connected and armed default download capture")

    async def send_command(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 5.0
    ) -> dict[str, Any]:
        """Send a CDP command and strictly await response with matching ID."""
        if not self.agent_ws or self.shutting_down:
            raise RuntimeError("CDP proxy is not connected")

        async with self._lock:
            self._next_cmd_id += 1
            cid = self._next_cmd_id

        req = {"id": cid, "method": method, "params": params or {}}
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.pending_cmd_futures[cid] = fut

        try:
            await self.agent_ws.send(json.dumps(req))
            resp = await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self.pending_cmd_futures.pop(cid, None)
            if not fut.done():
                fut.cancel()
        if "error" in resp or "result" not in resp:
            raise RuntimeError("CDP command was not acknowledged")
        return resp

    async def rearm_download_capture(self, timeout: float = 5.0) -> None:
        """Arm or restore default download capture and strictly await CDP ACK."""
        Path(self.default_download_dir).mkdir(parents=True, exist_ok=True)
        resp = await self.send_command(
            "Browser.setDownloadBehavior",
            {
                "behavior": "allowAndName",
                "downloadPath": self.default_download_dir,
                "eventsEnabled": True,
            },
            timeout=timeout,
        )
        self.rearm_count += 1
        logger.info(
            "Download capture rearmed to %s (count=%d, resp=%s)",
            self.default_download_dir,
            self.rearm_count,
            resp,
        )

    async def close_browser(self, timeout: float = 5.0) -> dict[str, Any]:
        """Request Chrome to close gracefully via CDP Browser.close."""
        logger.info("Sending CDP Browser.close command...")
        try:
            return await self.send_command("Browser.close", timeout=timeout)
        except Exception as e:  # noqa: BLE001 - graceful browser close failure returns unconfirmed status safely
            logger.warning("Browser.close was not acknowledged (%s)", type(e).__name__)
            return {"error": "close_unconfirmed"}

    async def _listen_events(self) -> None:
        """Background loop reading CDP messages and tracking download events."""
        try:
            async for raw_msg in self.agent_ws:
                msg = json.loads(raw_msg)
                msg_id = msg.get("id")
                if msg_id in self.pending_cmd_futures:
                    fut = self.pending_cmd_futures.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)

                method = msg.get("method", "")
                if method == "Browser.downloadWillBegin":
                    self._handle_download_will_begin(msg.get("params", {}))
                elif method == "Browser.downloadProgress":
                    self._handle_download_progress(msg.get("params", {}))
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001 - background CDP listener error isolated from manager lifecycle
            if not self.shutting_down:
                logger.error("CDP event listener error (%s)", type(e).__name__)
        finally:
            for future in self.pending_cmd_futures.values():
                if not future.done():
                    if self.shutting_down:
                        future.cancel()
                    else:
                        future.set_exception(RuntimeError("CDP event channel closed"))
            self.pending_cmd_futures.clear()

    def _handle_download_will_begin(self, params: dict[str, Any]) -> None:
        guid = params.get("guid", "")
        url = params.get("url")
        suggested_filename = params.get("suggestedFilename")
        self.active_downloads[guid] = {
            "guid": guid,
            "url": url,
            "suggested_filename": suggested_filename,
            "download_path": str(Path(self.default_download_dir) / guid),
            "state": "in_progress",
            "received_bytes": 0,
            "total_bytes": 0,
        }
        event = DownloadEventRecord(
            event_id=f"dl_begin_{uuid.uuid4().hex[:16]}",
            profile_id=self.profile_id,
            runtime_instance_id=self.runtime_instance_id,
            guid=guid,
            url=url,
            suggested_filename=suggested_filename,
            download_path=self.active_downloads[guid]["download_path"],
            state="in_progress",
            received_bytes=0,
            total_bytes=0,
        )
        self.event_storage.save_download_event(event)

    def _handle_download_progress(self, params: dict[str, Any]) -> None:
        guid = params.get("guid", "")
        state = params.get("state", "in_progress")
        received = int(params.get("receivedBytes", 0))
        total = int(params.get("totalBytes", 0))

        dl = self.active_downloads.get(guid)
        if dl:
            dl["received_bytes"] = received
            dl["total_bytes"] = total
            dl["state"] = state

        if state in ("completed", "canceled"):
            candidate = params.get("filePath") or (
                dl.get("download_path")
                if dl
                else str(Path(self.default_download_dir) / guid)
            )
            captured_path = None
            if candidate:
                try:
                    path = Path(candidate).resolve()
                    if (
                        path.is_relative_to(Path(self.default_download_dir).resolve())
                        and path.is_file()
                    ):
                        captured_path = str(path)
                except (OSError, ValueError):
                    pass
            event = DownloadEventRecord(
                event_id=f"dl_{state}_{uuid.uuid4().hex[:16]}",
                profile_id=self.profile_id,
                runtime_instance_id=self.runtime_instance_id,
                guid=guid,
                url=dl.get("url") if dl else None,
                suggested_filename=dl.get("suggested_filename") if dl else None,
                download_path=captured_path,
                state="completed" if state == "completed" else "canceled",
                received_bytes=received,
                total_bytes=total,
            )
            self.event_storage.save_download_event(event)
            self.active_downloads.pop(guid, None)

    async def close(self) -> None:
        """Clean shutdown of CDP manager."""
        self.shutting_down = True
        if self._event_listener_task:
            self._event_listener_task.cancel()
            await self._event_listener_task
        if self.agent_ws:
            await self.agent_ws.close()
        for fut in self.pending_cmd_futures.values():
            if not fut.done():
                fut.cancel()
        self.pending_cmd_futures.clear()
        logger.info("CDP proxy manager closed")
