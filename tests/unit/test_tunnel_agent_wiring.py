"""Agent UDS /cdp tunnel mediation end-to-end against a fake browser WS (t030).

The pure filter rules live in test_tunnel_filter.py; here the production
``websocket_cdp_proxy`` path is exercised: rejected commands never reach the
browser, owned-target closes pass through, and session scripts are removed
on disconnect.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import uvicorn
import websockets

from cbrowser.runtime_agent.agent import create_agent_app


class _FakeBrowser:
    """Records CDP methods and answers creation/script-registration calls."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self._server = None
        self.targets: dict[str, dict] = {
            "t-user": {"targetId": "t-user", "type": "page"},
            "t-agent-1": {"targetId": "t-agent-1", "type": "page"},
        }

    async def _handler(self, ws) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            self.received.append(msg)
            method = msg.get("method")
            params = msg.get("params", {}) or {}
            if method == "Target.getTargets":
                await ws.send(
                    json.dumps(
                        {
                            "id": msg["id"],
                            "result": {"targetInfos": list(self.targets.values())},
                        }
                    )
                )
            elif method == "Target.createTarget":
                await ws.send(
                    json.dumps(
                        {"id": msg["id"], "result": {"targetId": "t-agent-1"}}
                    )
                )
            elif method == "Page.addScriptToEvaluateOnNewDocument":
                await ws.send(
                    json.dumps(
                        {"id": msg["id"], "result": {"identifier": "script-1"}}
                    )
                )
            elif method == "Target.closeTarget":
                self.targets.pop(params.get("targetId"), None)
                await ws.send(json.dumps({"id": msg["id"], "result": {}}))
            else:
                await ws.send(json.dumps({"id": msg["id"], "result": {}}))

    async def start(self, port: int) -> None:
        self._server = await websockets.serve(self._handler, "127.0.0.1", port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    def methods(self) -> list[str]:
        return [m.get("method", "") for m in self.received]


class _UvicornThread:
    def __init__(self, app, port: int) -> None:
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> int:
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return int(self.server.config.port)
            time.sleep(0.05)
        raise RuntimeError("uvicorn did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_tunnel_rejects_close_and_mediates_closes(tmp_path: Path) -> None:
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True, exist_ok=True)
    download_dir = tmp_path / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)

    browser_port = _free_port()
    fake = _FakeBrowser()
    await fake.start(browser_port)
    (run_dir / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": "p1",
                "runtime_instance_id": "i1",
                "config_version": 1,
                "cdp_port": browser_port,
                "browser_ws_url": f"ws://127.0.0.1:{browser_port}/devtools/browser/x",
                "browser_pid": 1,
                "runner_pid": 1,
            }
        ),
        encoding="utf-8",
    )
    mock_cdp = MagicMock()
    mock_cdp.rearm_count = 0
    mock_cdp.capture_alive = True
    mock_cdp.rearm_download_capture = AsyncMock()
    mock_cdp.reconcile_downloads = AsyncMock()
    app = create_agent_app(
        run_dir=run_dir,
        default_download_dir=download_dir,
        cdp_proxy=mock_cdp,
    )
    api_port = _free_port()
    server = _UvicornThread(app, api_port)
    server.start()
    try:
        async with websockets.connect(
            f"ws://127.0.0.1:{api_port}/cdp", proxy=None
        ) as client:
            # Browser.close is rejected and never reaches the browser.
            await client.send(json.dumps({"id": 1, "method": "Browser.close"}))
            resp = json.loads(await asyncio.wait_for(client.recv(), timeout=5))
            assert resp["id"] == 1
            assert resp["error"]["code"] == -32000
            assert "Browser.close" not in fake.methods()

            # Download-behavior override is rejected and never forwarded.
            await client.send(
                json.dumps(
                    {
                        "id": 2,
                        "method": "Browser.setDownloadBehavior",
                        "params": {"behavior": "allow"},
                    }
                )
            )
            resp = json.loads(await asyncio.wait_for(client.recv(), timeout=5))
            assert resp["id"] == 2
            assert resp["error"]["code"] == -32000
            assert "Browser.setDownloadBehavior" not in fake.methods()

            # With two pages known, closing one is forwarded (tab-close
            # authorization lives in the executor ledger, not the tunnel).
            await client.send(json.dumps({"id": 3, "method": "Target.getTargets"}))
            resp = json.loads(await asyncio.wait_for(client.recv(), timeout=5))
            assert len(resp["result"]["targetInfos"]) == 2
            await client.send(
                json.dumps(
                    {
                        "id": 4,
                        "method": "Target.closeTarget",
                        "params": {"targetId": "t-user"},
                    }
                )
            )
            resp = json.loads(await asyncio.wait_for(client.recv(), timeout=5))
            assert "error" not in resp
            assert fake.methods().count("Target.closeTarget") == 1

            # Now only one page is known: closing it is refused so the
            # browser cannot be stopped via last-tab close.
            await client.send(json.dumps({"id": 5, "method": "Target.getTargets"}))
            resp = json.loads(await asyncio.wait_for(client.recv(), timeout=5))
            assert len(resp["result"]["targetInfos"]) == 1
            await client.send(
                json.dumps(
                    {
                        "id": 6,
                        "method": "Target.closeTarget",
                        "params": {"targetId": "t-agent-1"},
                    }
                )
            )
            resp = json.loads(await asyncio.wait_for(client.recv(), timeout=5))
            assert resp["id"] == 6
            assert resp["error"]["code"] == -32000
            assert "last_tab_protected" in resp["error"]["message"]
            assert fake.methods().count("Target.closeTarget") == 1

            # Register a session script; disconnect must remove it.
            await client.send(
                json.dumps(
                    {
                        "id": 7,
                        "method": "Page.addScriptToEvaluateOnNewDocument",
                        "params": {"source": "1"},
                    }
                )
            )
            resp = json.loads(await asyncio.wait_for(client.recv(), timeout=5))
            assert resp["result"]["identifier"] == "script-1"
        # Client closed: tunnel teardown sends the removal before closing.
        deadline = time.monotonic() + 5
        while (
            "Page.removeScriptToEvaluateOnNewDocument" not in fake.methods()
            and time.monotonic() < deadline
        ):
            await asyncio.sleep(0.05)
        assert "Page.removeScriptToEvaluateOnNewDocument" in fake.methods()
    finally:
        server.stop()
        await fake.stop()
