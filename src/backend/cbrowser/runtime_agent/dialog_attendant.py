"""Resident dialog attendant (t031, ADR 019).

The attendant is a component of the runtime Agent process, not a new
daemon: it holds one service CDP connection to the browser and keeps a
no-op dialog listener on every page target. Presence of the listener
prevents Chrome from auto-dismissing an unclaimed dialog (t030
evidence: with no session claiming dialog handling, Chrome dismisses
at open time; a lingering listener keeps the dialog open). The
attendant never answers on its own: it only preserves the dialog so
the human can answer it from the video stream after a takeover, or a
later agent session can answer it through the control-plane answer
path (t031 chain evidence: a session attached AFTER a dialog opened
cannot answer it -- Chrome reports "No dialog is showing" and its
Page.enable hangs behind the modal dialog -- so only the attendant's
pre-existing session can answer a held dialog).

Lifecycle (control-aware by construction, not by control-state reads):
- Armed when the Agent's /cdp proxy accepts a client (every tunneled
  automation session passes through that proxy, on both the API and
  the Supervisor path). Arming is idempotent.
- Released by the Supervisor close-tunnels cascade (Agent /control
  action ``release_attendant``) during a takeover, on Agent stop, and
  when the service connection drops. A later /cdp client re-arms.
- While released, dialogs follow Chrome's default behavior: an already-open
  dialog stays visible in the video stream for the human; a dialog
  that opens with no listener is auto-dismissed by Chrome.

The service connection is a direct browser websocket, not a tunnel
client, so tunnel filtering does not apply to it. It sends no
mutating commands: Target discovery/attach and Page.enable only.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from typing import Any

logger = logging.getLogger("cbrowser.runtime_agent.dialog_attendant")


class HeldDialog:
    def __init__(
        self,
        target_id: str,
        dialog_type: str,
        message: str,
        url: str | None,
        session_id: str | None = None,
    ):
        self.target_id = target_id
        self.dialog_type = dialog_type
        self.message = message
        self.url = url
        self.session_id = session_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "type": self.dialog_type,
            "message": self.message,
            "url": self.url,
        }


class DialogAttendant:
    """Pure dialog state machine (no I/O; unit-tested directly)."""

    def __init__(self) -> None:
        self._held: dict[str, HeldDialog] = {}
        self._session_targets: dict[str, str] = {}
        self.released = False

    def note_attached(self, session_id: str, target_id: str) -> None:
        self._session_targets[session_id] = target_id

    def note_detached(self, session_id: str) -> None:
        self._session_targets.pop(session_id, None)
        self._held.pop(session_id, None)

    def note_opening(self, session_id: str, params: dict[str, Any]) -> None:
        target_id = self._session_targets.get(session_id)
        if target_id is None:
            return
        self._held[session_id] = HeldDialog(
            target_id=target_id,
            dialog_type=str(params.get("type", "")),
            message=str(params.get("message", "")),
            url=params.get("url"),
            session_id=session_id,
        )
        logger.info(
            "Dialog attendant holding dialog: target=%s type=%s",
            target_id,
            params.get("type", ""),
        )

    def note_closed(self, session_id: str) -> None:
        self._held.pop(session_id, None)

    def held_dialogs(self) -> list[HeldDialog]:
        return list(self._held.values())

    def held_for_target(self, target_id: str) -> HeldDialog | None:
        for record in self._held.values():
            if record.target_id == target_id:
                return record
        return None

    def release(self) -> None:
        """Drop all held state; the service connection detaches."""
        self._held.clear()
        self._session_targets.clear()
        self.released = True

    def rearm(self) -> None:
        self.released = False


class DialogAttendantService:
    """Async service connection driving a DialogAttendant."""

    def __init__(
        self,
        attendant: DialogAttendant | None = None,
        *,
        connect=None,
    ):
        self.attendant = attendant or DialogAttendant()
        self._connect = connect
        self._task: asyncio.Task | None = None
        self._ws = None
        self._id_counter = itertools.count(1)
        self._stop_event: asyncio.Event | None = None
        self._waiters: dict[int, asyncio.Future] = {}

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def arm(self, browser_ws_url: str) -> None:
        """Start the service connection unless already running."""
        if self.running:
            return
        self.attendant.rearm()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Dialog attendant arm without a running loop")
            return
        self._task = loop.create_task(self._run(browser_ws_url))

    async def release(self) -> None:
        """Stop the service connection and drop held state."""
        self.attendant.release()
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001 - best-effort close
                pass
            self._ws = None

    async def answer_dialog(
        self,
        target_id: str,
        accept: bool,
        prompt_text: str | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any] | None:
        """Answer a held dialog on the attendant's own session.

        Only the attendant's pre-existing session can answer a held
        dialog (t031 chain evidence: a later session gets "No dialog
        is showing" and its Page.enable hangs behind the modal dialog).
        Returns the answered dialog record, or None when no dialog is
        held for the target or the service connection is down.
        """
        record = self.attendant.held_for_target(target_id)
        if record is None or record.session_id is None:
            return None
        if self._ws is None or not self.running:
            return None
        params: dict[str, Any] = {"accept": accept}
        if prompt_text is not None:
            params["promptText"] = prompt_text
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        # Register the waiter BEFORE sending: the response may arrive
        # before the send coroutine yields back to this task.
        msg_id = next(self._id_counter)
        waiter: asyncio.Future = loop.create_future()
        self._waiters[msg_id] = waiter
        await self._send(
            "Page.handleJavaScriptDialog",
            params,
            session_id=record.session_id,
            msg_id=msg_id,
        )
        try:
            resp = await asyncio.wait_for(waiter, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._waiters.pop(msg_id, None)
            return None
        if not isinstance(resp, dict) or "error" in resp:
            return None
        answered = record.to_dict()
        self.attendant.note_closed(record.session_id)
        return answered

    async def _send(self, method: str, params: dict | None = None,
                    session_id: str | None = None,
                    msg_id: int | None = None) -> int:
        if msg_id is None:
            msg_id = next(self._id_counter)
        cmd: dict[str, Any] = {"id": msg_id, "method": method}
        if params is not None:
            cmd["params"] = params
        if session_id is not None:
            cmd["sessionId"] = session_id
        await self._ws.send(json.dumps(cmd))
        return msg_id

    async def _handle_response(
        self, msg: dict, targets_id: int, pending_attach: dict[int, str]
    ) -> None:
        """Deliver one awaited CDP response (t031_code_f007 split)."""
        waiter = self._waiters.pop(msg["id"], None)
        if waiter is not None and not waiter.done():
            waiter.set_result(msg)
            return
        # getTargets response: attach to every page target.
        if msg["id"] == targets_id and isinstance(msg.get("result"), dict):
            for info in msg["result"].get("targetInfos", []):
                if info.get("type") != "page":
                    continue
                target_id = info.get("targetId")
                if not isinstance(target_id, str):
                    continue
                attach_id = await self._send(
                    "Target.attachToTarget",
                    {
                        "targetId": target_id,
                        "flatten": True,
                    },
                )
                pending_attach[attach_id] = target_id
        elif msg["id"] in pending_attach:
            target_id = pending_attach.pop(msg["id"])
            session_id = (msg.get("result") or {}).get("sessionId")
            if isinstance(session_id, str):
                self.attendant.note_attached(session_id, target_id)
                await self._send("Page.enable", session_id=session_id)

    async def _handle_event(
        self, msg: dict, pending_attach: dict[int, str]
    ) -> None:
        """Dispatch one CDP event (t031_code_f007 split)."""
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "Target.targetCreated":
            info = params.get("targetInfo") or {}
            if info.get("type") == "page":
                target_id = info.get("targetId")
                if isinstance(target_id, str):
                    attach_id = await self._send(
                        "Target.attachToTarget",
                        {"targetId": target_id, "flatten": True},
                    )
                    pending_attach[attach_id] = target_id
        elif method == "Target.attachedToTarget":
            session_id = params.get("sessionId")
            info = params.get("targetInfo") or {}
            target_id = info.get("targetId")
            if isinstance(session_id, str) and isinstance(target_id, str):
                self.attendant.note_attached(session_id, target_id)
                await self._send("Page.enable", session_id=session_id)
        elif method == "Target.detachedFromTarget":
            session_id = params.get("sessionId")
            if isinstance(session_id, str):
                self.attendant.note_detached(session_id)
        elif method == "Page.javascriptDialogOpening":
            session_id = msg.get("sessionId")
            if isinstance(session_id, str):
                self.attendant.note_opening(session_id, params)
        elif method == "Page.javascriptDialogClosed":
            session_id = msg.get("sessionId")
            if isinstance(session_id, str):
                self.attendant.note_closed(session_id)

    def _settle_waiters(self) -> None:
        waiters = list(self._waiters.values())
        self._waiters.clear()
        for waiter in waiters:
            if not waiter.done():
                waiter.cancel()

    async def _run(self, browser_ws_url: str) -> None:
        import websockets

        connect = self._connect or websockets.connect
        try:
            self._ws = await connect(
                browser_ws_url,
                max_size=32 * 1024 * 1024,
                ping_interval=10,
                ping_timeout=10,
            )
            await self._send("Target.setDiscoverTargets", {"discover": True})
            targets_id = await self._send("Target.getTargets")
            pending_attach: dict[int, str] = {}
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                if "id" in msg and isinstance(msg.get("id"), int):
                    # Awaited request response: deliver to its waiter
                    # first (answer_dialog); the discovery/attach
                    # correlation below handles the rest.
                    await self._handle_response(
                        msg, targets_id, pending_attach
                    )
                    continue
                await self._handle_event(msg, pending_attach)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - attendant failure is non-fatal
            logger.warning(
                "Dialog attendant service ended: error_type=%s",
                type(exc).__name__,
            )
        finally:
            # t031_code_f006: a dropped service connection must not
            # leave stale held dialogs behind: their session ids are
            # dead (a new session cannot answer an already-open dialog
            # per the chain evidence), so peek would report dialogs no
            # one can answer. A later re-arm clears the released flag.
            self.attendant.release()
            self._settle_waiters()
            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:  # noqa: BLE001 - best-effort close
                    pass
                self._ws = None
