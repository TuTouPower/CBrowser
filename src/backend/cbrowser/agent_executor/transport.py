"""Minimal async CDP client for the t030 agent executor.

One websocket, one reader task.  Commands are concurrent: each command
awaits only its own response future, so answering a dialog never waits
behind the command that triggered it (p032 pending-command requirement).
Events (``method`` messages) are handed to registered handlers without
blocking the reader.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable


class CdpError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class TunnelRejectedError(CdpError):
    """The tunnel filter refused a command (stable CBrowser error)."""


class CdpTimeoutError(CdpError):
    """A CDP command did not answer within its timeout."""


class CdpDisconnectedError(CdpError):
    pass


_DISCONNECT_MESSAGE = "CDP transport disconnected"


def _consume_future_exception(fut: asyncio.Future) -> None:
    if not fut.cancelled():
        fut.exception()


class CdpClient:
    def __init__(
        self,
        ws_url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.ws_url = ws_url
        self.headers = headers or {}
        self._ws: Any = None
        self._next_id = 0
        self._pending: dict[tuple[str | None, int], asyncio.Future] = {}
        self._handlers: list[Callable[[dict], None]] = []
        self._reader_task: asyncio.Task | None = None

    def on_event(self, handler: Callable[[dict], None]) -> None:
        self._handlers.append(handler)

    async def connect(self) -> None:
        import websockets

        kwargs: dict[str, Any] = {
            "max_size": 32 * 1024 * 1024,
            "ping_interval": 10,
            "ping_timeout": 10,
        }
        if self.headers:
            kwargs["additional_headers"] = self.headers
        # No proxy: the executor always talks to the local tunnel.
        kwargs["proxy"] = None
        self._ws = await websockets.connect(self.ws_url, **kwargs)
        self._reader_task = asyncio.create_task(self._read_loop())

    def _settle_pending(self) -> None:
        pending = list(self._pending.values())
        self._pending.clear()
        for fut in pending:
            if fut.done():
                continue
            fut.set_exception(CdpDisconnectedError(_DISCONNECT_MESSAGE))
            fut.add_done_callback(_consume_future_exception)

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                msg_id = msg.get("id")
                if isinstance(msg_id, int):
                    key = (msg.get("sessionId"), msg_id)
                    fut = self._pending.pop(key, None)
                    if fut is None:
                        # Ids are allocated globally unique, so an id-only
                        # match is unambiguous even when a peer does not
                        # echo sessionId on session-command responses.
                        for pending_key in list(self._pending):
                            if pending_key[1] == msg_id:
                                fut = self._pending.pop(pending_key)
                                break
                    if fut is not None and not fut.done():
                        fut.set_result(msg)
                        continue
                if "method" in msg:
                    for handler in list(self._handlers):
                        try:
                            handler(msg)
                        except Exception:  # noqa: BLE001 - a handler must not kill the reader
                            continue
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - reader death surfaces on next send
            pass
        finally:
            self._settle_pending()

    async def send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> tuple[tuple[str | None, int], asyncio.Future]:
        """Send a command without awaiting its response.

        Returns the pending key and future so the caller can wait with
        its own conditions (e.g. give up early when a dialog opens).
        The caller owns the future: either await it or drop it with
        :meth:`drop_pending` (a late response is then ignored).
        """
        if self._ws is None:
            raise CdpError("CDP client is not connected")
        self._next_id += 1
        msg_id = self._next_id
        msg: dict[str, Any] = {"id": msg_id, "method": method}
        if params:
            msg["params"] = params
        if session_id is not None:
            msg["sessionId"] = session_id
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        key = (session_id, msg_id)
        self._pending[key] = fut
        try:
            await self._ws.send(json.dumps(msg))
        except Exception as exc:
            self._settle_pending()
            raise CdpDisconnectedError(_DISCONNECT_MESSAGE) from exc
        return key, fut

    def drop_pending(self, key: tuple[str | None, int]) -> None:
        """Forget a pending command; its late response is ignored."""
        self._pending.pop(key, None)

    @staticmethod
    def response_error(resp: dict[str, Any]) -> Exception | None:
        """Map a command response to an error, or None on success."""
        if "error" not in resp:
            return None
        error = resp["error"] or {}
        message = str(error.get("message", "CDP error"))
        if message.startswith("CBrowser tunnel:"):
            return TunnelRejectedError(message, error.get("code"))
        return CdpError(message, error.get("code"))

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        key, fut = await self.send_request(method, params, session_id)
        try:
            resp = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(key, None)
            raise CdpTimeoutError(
                f"CDP command {method} timed out after {timeout}s"
            ) from None
        error = self.response_error(resp)
        if error is not None:
            raise error
        return resp.get("result", {})

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001 - best-effort close
                pass
            self._ws = None
        self._settle_pending()
