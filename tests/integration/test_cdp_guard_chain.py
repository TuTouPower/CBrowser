"""Integration: the health/CDP chain keeps working with cdp_port on the guard.

Proves that the guard-owned cdp_port still satisfies the UDS Agent's
check_browser probe and /cdp/version endpoint, while the internal
browser_ws_url keeps reaching Chrome directly (no Origin, never blocked by
the guard).
"""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import MagicMock

import httpx
import pytest
import websockets
from aiohttp import WSMsgType, web

from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.runtime_agent.cdp_guard import CdpGuard


@asynccontextmanager
async def _chain() -> AsyncIterator[tuple[int, int]]:
    app = web.Application()

    async def version(request: web.Request) -> web.Response:
        return web.json_response(
            {
                "Browser": "Chrome/Mock",
                "webSocketDebuggerUrl": f"ws://{request.host}/devtools/browser/ABC",
            }
        )

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(request)
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                await ws.send_json(
                    {"id": data.get("id"), "result": {"product": "Chrome/Mock"}}
                )
        return ws

    app.router.add_get("/json/version", version)
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
        yield guard_port, chrome_port
    finally:
        await guard.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_health_cdp_version_and_internal_ws_survive_guard(
    tmp_path: Path,
) -> None:
    async with _chain() as (guard_port, chrome_port):
        runner_info = {
            "profile_id": "profile_chain",
            "runtime_instance_id": "instance_chain",
            "config_version": 1,
            "cdp_port": guard_port,
            "browser_ws_url": (
                f"ws://127.0.0.1:{chrome_port}/devtools/browser/ABC"
            ),
            "display": ":99",
        }
        (tmp_path / "runner_info.json").write_text(
            json.dumps(runner_info), encoding="utf-8"
        )

        cdp_proxy = MagicMock()
        cdp_proxy.capture_alive = True
        cdp_proxy.rearm_count = 0
        app = create_agent_app(
            run_dir=tmp_path,
            default_download_dir=tmp_path / "downloads",
            cdp_proxy=cdp_proxy,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://agent"
        ) as client:
            health = await client.get("/health")
            assert health.status_code == 200
            data = health.json()
            assert data["details"]["cdp_port"] == guard_port
            assert data["details"]["cdp_port"] != chrome_port
            assert data["browser_ready"] is True

            version = await client.get("/cdp/version")
            assert version.status_code == 200
            assert "Browser" in version.json()

        async with websockets.connect(
            runner_info["browser_ws_url"], open_timeout=5
        ) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
            reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert reply["result"]["product"] == "Chrome/Mock"
