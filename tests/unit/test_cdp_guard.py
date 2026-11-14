"""Unit tests for the CDP loopback Host/Origin boundary guard.

Tests drive the real guard server over loopback sockets against a mock Chrome
DevTools backend (HTTP + WebSocket), including raw malformed headers, so the
production request handler and both proxying paths are exercised end to end.
"""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlsplit

import pytest
import websockets
from aiohttp import WSMsgType, web
from websockets.exceptions import InvalidStatus

from cbrowser.runtime_agent.cdp_guard import (
    CdpGuard,
    host_is_allowed,
    origin_is_allowed,
    rewrite_json_ws_urls,
)


@asynccontextmanager
async def _serve() -> AsyncIterator[tuple[CdpGuard, int, int]]:
    app = web.Application()

    async def http_version(request: web.Request) -> web.Response:
        return web.json_response(
            {
                "Browser": "Chrome/Mock 999",
                "Protocol-Version": "1.3",
                "webSocketDebuggerUrl": (
                    f"ws://{request.host}/devtools/browser/ABC"
                ),
            }
        )

    async def http_list(request: web.Request) -> web.Response:
        return web.json_response(
            [
                {
                    "type": "page",
                    "webSocketDebuggerUrl": (
                        f"ws://{request.host}/devtools/page/XYZ"
                    ),
                }
            ]
        )

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(request)
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                await ws.send_json(
                    {"id": data.get("id"), "result": {"product": "Chrome/Mock 999"}}
                )
        return ws

    app.router.add_get("/json/version", http_version)
    app.router.add_get("/json/list", http_list)
    app.router.add_get("/{tail:.*}", ws_handler)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    chrome_port = sock.getsockname()[1]
    site = web.SockSite(runner, sock)
    await site.start()

    guard = CdpGuard(chrome_port)
    guard_port = await guard.start()
    try:
        yield guard, guard_port, chrome_port
    finally:
        await guard.close()
        await runner.cleanup()


async def _raw_http(port: int, header_lines: list[str], path: str = "/json/version") -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    request = (
        f"GET {path} HTTP/1.1\r\n"
        + "\r\n".join(header_lines)
        + "\r\n\r\n"
    )
    writer.write(request.encode("iso-8859-1"))
    await writer.drain()
    try:
        return await asyncio.wait_for(reader.read(), timeout=5)
    finally:
        writer.close()


def _status(data: bytes) -> int:
    return int(data.split(b"\r\n", 1)[0].split()[1])


def _body(data: bytes) -> bytes:
    return data.split(b"\r\n\r\n", 1)[1]


@pytest.mark.asyncio
async def test_valid_host_returns_200_and_retargets_ws_url() -> None:
    async with _serve() as (_guard, guard_port, chrome_port):
        data = await _raw_http(
            guard_port, [f"Host: 127.0.0.1:{guard_port}", "Connection: close"]
        )
        assert _status(data) == 200
        payload = json.loads(_body(data))
        assert payload["Browser"] == "Chrome/Mock 999"
        parts = urlsplit(payload["webSocketDebuggerUrl"])
        assert parts.scheme == "ws"
        assert parts.hostname == "127.0.0.1"
        assert parts.port == guard_port
        assert parts.port != chrome_port
        assert parts.path == "/devtools/browser/ABC"


@pytest.mark.asyncio
async def test_json_list_ws_urls_are_retargeted() -> None:
    async with _serve() as (_guard, guard_port, _chrome_port):
        data = await _raw_http(
            guard_port,
            [f"Host: 127.0.0.1:{guard_port}", "Connection: close"],
            path="/json/list",
        )
        assert _status(data) == 200
        payload = json.loads(_body(data))
        assert urlsplit(payload[0]["webSocketDebuggerUrl"]).port == guard_port


@pytest.mark.asyncio
async def test_valid_host_variants_are_accepted() -> None:
    async with _serve() as (_guard, guard_port, _chrome_port):
        for host in (
            "127.0.0.1",
            "localhost",
            "LOCALHOST",
            "LocalHost",
            "127.0.0.1:1234",
            "localhost:9999",
            f"127.0.0.1:{guard_port}",
        ):
            data = await _raw_http(guard_port, [f"Host: {host}", "Connection: close"])
            assert _status(data) == 200, host


@pytest.mark.asyncio
async def test_forged_hosts_rejected_403_without_version_leak() -> None:
    async with _serve() as (_guard, guard_port, _chrome_port):
        for host in (
            "rebinding.example",
            f"rebinding.example:{guard_port}",
            "127.0.0.1.evil.com",
            "localhost.evil.com",
            "[::1]",
            "10.0.0.5",
            f"localhost:{guard_port}@evil.com",
            "LOCALHOST.example.com",
        ):
            data = await _raw_http(guard_port, [f"Host: {host}", "Connection: close"])
            assert _status(data) == 403, host
            body = _body(data)
            assert b"Browser" not in body
            assert b"Chrome" not in body
            assert b"webSocketDebuggerUrl" not in body


@pytest.mark.asyncio
async def test_malformed_hosts_never_return_500() -> None:
    async with _serve() as (_guard, guard_port, _chrome_port):
        malformed = (
            "",
            "   ",
            "127.0.0.1:abc",
            "127.0.0.1:9222 extra",
            "\x00",
            "127.0.0.1:9222:9222",
            ":",
            "localhost:",
            "127.0.0.1:9222,evil.com",
        )
        for host in malformed:
            data = await _raw_http(guard_port, [f"Host: {host}", "Connection: close"])
            assert _status(data) == 403, repr(host)
        data = await _raw_http(
            guard_port,
            ["Host: 127.0.0.1", "Host: evil.com", "Connection: close"],
        )
        assert _status(data) == 403
        data = await _raw_http(guard_port, ["Connection: close"])
        assert _status(data) == 403


@pytest.mark.asyncio
async def test_ws_valid_origins_connect_and_forward_frames() -> None:
    async with _serve() as (_guard, guard_port, _chrome_port):
        uri = f"ws://127.0.0.1:{guard_port}/devtools/browser/ABC"
        for origin in (
            f"http://127.0.0.1:{guard_port}",
            "http://127.0.0.1",
            "http://localhost",
            "http://LOCALHOST:1234",
        ):
            async with websockets.connect(uri, origin=origin, open_timeout=5) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
                reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                assert reply["result"]["product"] == "Chrome/Mock 999", origin


@pytest.mark.asyncio
async def test_ws_bad_origins_rejected_403() -> None:
    async with _serve() as (_guard, guard_port, _chrome_port):
        uri = f"ws://127.0.0.1:{guard_port}/devtools/browser/ABC"
        for origin in (
            "https://malicious.example.com",
            "http://evil.com",
            "https://127.0.0.1",
            "null",
            "http://127.0.0.1.evil.com",
        ):
            with pytest.raises(InvalidStatus) as info:
                async with websockets.connect(uri, origin=origin, open_timeout=5):
                    pass
            assert info.value.response.status_code == 403, origin
        with pytest.raises(InvalidStatus) as info:
            async with websockets.connect(uri, open_timeout=5):
                pass
        assert info.value.response.status_code == 403


@pytest.mark.asyncio
async def test_ws_upgrade_forged_host_rejected_403() -> None:
    async with _serve() as (_guard, guard_port, _chrome_port):
        headers = [
            "Host: rebinding.example",
            "Upgrade: websocket",
            "Connection: Upgrade",
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
            "Sec-WebSocket-Version: 13",
        ]
        data = await _raw_http(
            guard_port, headers, path="/devtools/browser/ABC"
        )
        assert _status(data) == 403


@pytest.mark.asyncio
async def test_ws_upgrade_bad_origin_rejected_403() -> None:
    async with _serve() as (_guard, guard_port, _chrome_port):
        headers = [
            f"Host: 127.0.0.1:{guard_port}",
            "Origin: https://malicious.example.com",
            "Upgrade: websocket",
            "Connection: Upgrade",
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
            "Sec-WebSocket-Version: 13",
        ]
        data = await _raw_http(
            guard_port, headers, path="/devtools/browser/ABC"
        )
        assert _status(data) == 403


@pytest.mark.asyncio
async def test_guard_binds_loopback_only() -> None:
    async with _serve() as (guard, guard_port, _chrome_port):
        assert guard.bound_host == "127.0.0.1"
        assert guard.port == guard_port
        assert guard_port > 0


@pytest.mark.parametrize(
    "value,expected",
    [
        ("127.0.0.1", True),
        ("127.0.0.1:9222", True),
        ("localhost", True),
        ("LOCALHOST:9222", True),
        ("rebinding.example", False),
        ("rebinding.example:9222", False),
        ("127.0.0.1.evil.com", False),
        ("127.0.0.1:abc", False),
        ("", False),
        ("   ", False),
        ("\x00", False),
        (None, False),
        ("[::1]", False),
    ],
)
def test_host_is_allowed_table(value: str | None, expected: bool) -> None:
    assert host_is_allowed(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("http://127.0.0.1", True),
        ("http://127.0.0.1:9222", True),
        ("http://localhost", True),
        ("http://LOCALHOST:9222", True),
        ("https://malicious.example.com", False),
        ("https://127.0.0.1", False),
        ("http://evil.com", False),
        ("http://127.0.0.1.evil.com", False),
        ("null", False),
        ("", False),
        (None, False),
    ],
)
def test_origin_is_allowed_table(value: str | None, expected: bool) -> None:
    assert origin_is_allowed(value) is expected


def test_rewrite_json_ws_urls_rewrites_and_passthrough() -> None:
    body = json.dumps(
        [{"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/X?q=1"}]
    ).encode()
    rewritten = json.loads(rewrite_json_ws_urls(body, 5555))
    assert rewritten[0]["webSocketDebuggerUrl"] == (
        "ws://127.0.0.1:5555/devtools/page/X?q=1"
    )
    assert rewrite_json_ws_urls(b"not json", 5555) == b"not json"
