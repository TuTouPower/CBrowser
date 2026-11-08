"""A12: CdpClient must settle pending command futures on every connection
exit path (EOF, read exception, active close, send failure) with a stable
disconnect error, promptly (not the 30s timeout), without double-setting
done futures or producing unretrieved-exception warnings."""

from __future__ import annotations

import asyncio
import gc
import json

import pytest
from cbrowser.agent_executor.transport import (
    CdpClient,
    CdpError,
    TunnelRejectedError,
)


class _FakeWs:
    def __init__(
        self,
        inbound=None,
        *,
        block=False,
        send_error=None,
        read_error=None,
    ):
        self._queue: asyncio.Queue = asyncio.Queue()
        for msg in inbound or []:
            self._queue.put_nowait(json.dumps(msg))
        if not block:
            self._queue.put_nowait(None)
        self.sent: list[dict] = []
        self.closed = False
        self.send_error = send_error
        self.read_error = read_error

    async def send(self, text: str) -> None:
        self.sent.append(json.loads(text))
        if self.send_error is not None:
            raise self.send_error

    async def close(self) -> None:
        self.closed = True

    def feed(self, msg: dict) -> None:
        self._queue.put_nowait(json.dumps(msg))

    def eof(self) -> None:
        self._queue.put_nowait(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.read_error is not None:
            exc, self.read_error = self.read_error, None
            raise exc
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item


def _assert_disconnect(fut: asyncio.Future) -> None:
    assert fut.done(), "pending future was not settled on disconnect"
    exc = fut.exception()
    assert isinstance(exc, CdpError)
    assert str(exc) == "CDP transport disconnected"


@pytest.mark.asyncio
async def test_a12_eof_settles_pending_futures() -> None:
    ws = _FakeWs(inbound=[])
    client = CdpClient("ws://unused")
    client._ws = ws
    _k1, f1 = await client.send_request("Cmd.one")
    _k2, f2 = await client.send_request("Cmd.two", session_id="sess")
    loop = asyncio.get_running_loop()
    done = loop.create_future()
    done.set_result({"id": 99, "result": {}})
    client._pending[("s", 99)] = done
    reader = asyncio.create_task(client._read_loop())
    await asyncio.wait_for(reader, timeout=1.0)
    _assert_disconnect(f1)
    _assert_disconnect(f2)
    assert done.result() == {"id": 99, "result": {}}
    assert client._pending == {}


@pytest.mark.asyncio
async def test_a12_read_exception_settles_pending_futures() -> None:
    ws = _FakeWs(inbound=[], read_error=RuntimeError("read boom"))
    client = CdpClient("ws://unused")
    client._ws = ws
    _key, fut = await client.send_request("Cmd.one")
    reader = asyncio.create_task(client._read_loop())
    await asyncio.wait_for(reader, timeout=1.0)
    _assert_disconnect(fut)
    assert client._pending == {}


@pytest.mark.asyncio
async def test_a12_active_close_settles_pending_futures() -> None:
    ws = _FakeWs(inbound=[], block=True)
    client = CdpClient("ws://unused")
    client._ws = ws
    client._reader_task = asyncio.create_task(client._read_loop())
    _k1, f1 = await client.send_request("Cmd.one")
    _k2, f2 = await client.send_request("Cmd.two")
    await client.close()
    _assert_disconnect(f1)
    _assert_disconnect(f2)
    assert client._pending == {}
    assert ws.closed is True


@pytest.mark.asyncio
async def test_a12_send_failure_settles_pending_futures() -> None:
    ws = _FakeWs(inbound=[], block=True)
    client = CdpClient("ws://unused")
    client._ws = ws
    _key, existing = await client.send_request("Cmd.ok")
    ws.send_error = RuntimeError("send boom")
    with pytest.raises(CdpError) as exc_info:
        await client.send_request("Cmd.fail")
    assert "disconnected" in str(exc_info.value).lower()
    _assert_disconnect(existing)
    assert client._pending == {}


@pytest.mark.asyncio
async def test_a12_concurrent_commands_keep_distinguishable_errors() -> None:
    ws = _FakeWs(
        inbound=[
            {
                "id": 1,
                "error": {"message": "CBrowser tunnel: blocked", "code": -32000},
            }
        ]
    )
    client = CdpClient("ws://unused")
    client._ws = ws
    _k1, f1 = await client.send_request("Cmd.one")
    _k2, f2 = await client.send_request("Cmd.two")
    reader = asyncio.create_task(client._read_loop())
    await asyncio.wait_for(reader, timeout=1.0)
    assert f1.done()
    err1 = CdpClient.response_error(f1.result())
    assert isinstance(err1, TunnelRejectedError)
    _assert_disconnect(f2)
    assert client._pending == {}


@pytest.mark.asyncio
async def test_a12_send_does_not_wait_full_timeout_on_eof() -> None:
    ws = _FakeWs(inbound=[], block=True)
    client = CdpClient("ws://unused")
    client._ws = ws
    client._reader_task = asyncio.create_task(client._read_loop())
    send_task = asyncio.create_task(client.send("Cmd.slow", timeout=30.0))
    for _ in range(100):
        if client._pending:
            break
        await asyncio.sleep(0.01)
    assert client._pending
    ws.eof()
    with pytest.raises(CdpError) as exc_info:
        await asyncio.wait_for(send_task, timeout=1.0)
    assert "disconnected" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_a12_no_unretrieved_exception_warning() -> None:
    loop = asyncio.get_running_loop()
    contexts: list[dict] = []
    old = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, ctx: contexts.append(ctx))
    try:
        ws = _FakeWs(inbound=[])
        client = CdpClient("ws://unused")
        client._ws = ws
        _key, fut = await client.send_request("Cmd.orphan")
        reader = asyncio.create_task(client._read_loop())
        await asyncio.wait_for(reader, timeout=1.0)
        del fut
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        gc.collect()
        await asyncio.sleep(0)
    finally:
        loop.set_exception_handler(old)
    assert [
        c
        for c in contexts
        if "never retrieved" in str(c.get("message", "")).lower()
    ] == []
