"""A12: DialogAttendantService must cancel/fail-settle pending answer
waiters and clear the collection on every _run exit path, so a dialog
answer cannot hang for the full 30s fallback. Already-done futures are
not double-set; no unretrieved-exception warnings (waiters are cancelled,
not left with unretrieved exceptions)."""

from __future__ import annotations

import asyncio
import json

import pytest
from cbrowser.runtime_agent.dialog_attendant import DialogAttendantService


class _FakeWs:
    def __init__(
        self,
        inbound=None,
        *,
        block=False,
        respond=False,
        fail_exc=None,
    ):
        self._queue: asyncio.Queue = asyncio.Queue()
        for msg in inbound or []:
            self._queue.put_nowait(json.dumps(msg))
        if not block:
            self._queue.put_nowait(None)
        self.sent: list[dict] = []
        self.closed = False
        self.respond = respond
        self.fail_exc = fail_exc

    async def send(self, text: str) -> None:
        msg = json.loads(text)
        self.sent.append(msg)
        if self.respond and msg.get("method") == "Page.handleJavaScriptDialog":
            self._queue.put_nowait(
                json.dumps({"id": msg["id"], "result": {}})
            )

    async def close(self) -> None:
        self.closed = True

    def feed(self, msg: dict) -> None:
        self._queue.put_nowait(json.dumps(msg))

    def eof(self) -> None:
        self._queue.put_nowait(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.fail_exc is not None:
            exc, self.fail_exc = self.fail_exc, None
            raise exc
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item


def _service(ws: _FakeWs) -> DialogAttendantService:
    async def connect(url: str, **kwargs):
        return ws

    return DialogAttendantService(connect=connect)


@pytest.mark.asyncio
async def test_a12_eof_cancels_waiters_and_clears_collection() -> None:
    ws = _FakeWs(inbound=[])
    service = _service(ws)
    loop = asyncio.get_running_loop()
    w1 = loop.create_future()
    w2 = loop.create_future()
    done = loop.create_future()
    done.set_result({"id": 99, "result": {}})
    service._waiters[1] = w1
    service._waiters[2] = w2
    service._waiters[3] = done
    service.attendant.note_attached("s1", "page-1")
    service.attendant.note_opening("s1", {"type": "alert", "message": "x"})
    task = asyncio.create_task(service._run("ws://browser"))
    await asyncio.wait_for(task, timeout=1.0)
    assert w1.done() and w1.cancelled()
    assert w2.done() and w2.cancelled()
    assert done.result() == {"id": 99, "result": {}}
    assert service._waiters == {}
    assert service.attendant.held_dialogs() == []


@pytest.mark.asyncio
async def test_a12_read_exception_cancels_waiters() -> None:
    ws = _FakeWs(inbound=[], fail_exc=RuntimeError("read boom"))
    service = _service(ws)
    loop = asyncio.get_running_loop()
    waiter = loop.create_future()
    service._waiters[1] = waiter
    task = asyncio.create_task(service._run("ws://browser"))
    await asyncio.wait_for(task, timeout=1.0)
    assert waiter.cancelled()
    assert service._waiters == {}


@pytest.mark.asyncio
async def test_a12_task_cancel_cancels_waiters() -> None:
    ws = _FakeWs(inbound=[], block=True)
    service = _service(ws)
    loop = asyncio.get_running_loop()
    waiter = loop.create_future()
    service._waiters[1] = waiter
    task = asyncio.create_task(service._run("ws://browser"))
    for _ in range(100):
        if service._ws is not None:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert waiter.cancelled()
    assert service._waiters == {}


@pytest.mark.asyncio
async def test_a12_normal_response_keeps_distinguishable_result() -> None:
    ws = _FakeWs(inbound=[{"id": 7, "result": {"ok": True}}])
    service = _service(ws)
    loop = asyncio.get_running_loop()
    answered = loop.create_future()
    pending = loop.create_future()
    service._waiters[7] = answered
    service._waiters[8] = pending
    task = asyncio.create_task(service._run("ws://browser"))
    await asyncio.wait_for(task, timeout=1.0)
    assert answered.result() == {"id": 7, "result": {"ok": True}}
    assert pending.cancelled()
    assert service._waiters == {}


@pytest.mark.asyncio
async def test_a12_answer_dialog_returns_promptly_on_disconnect() -> None:
    ws = _FakeWs(inbound=[], block=True, respond=False)
    service = _service(ws)
    service.attendant.note_attached("s1", "page-1")
    service.attendant.note_opening("s1", {"type": "alert", "message": "x"})
    service.arm("ws://browser/devtools")
    answer_task = None
    try:
        for _ in range(100):
            if service._ws is not None and len(ws.sent) >= 2:
                break
            await asyncio.sleep(0.01)
        answer_task = asyncio.create_task(
            service.answer_dialog("page-1", accept=True)
        )
        for _ in range(100):
            if service._waiters:
                break
            await asyncio.sleep(0.01)
        assert service._waiters
        ws.eof()
        for _ in range(50):
            if service._waiters == {}:
                break
            await asyncio.sleep(0.01)
        assert service._waiters == {}
        result = await asyncio.wait_for(answer_task, timeout=1.0)
        assert result is None
    finally:
        ws.eof()
        if answer_task is not None and not answer_task.done():
            answer_task.cancel()
        await service.release()
