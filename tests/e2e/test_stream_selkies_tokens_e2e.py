"""Real Docker E2E test suite for AC-008 (Dual mode disabled) & AC-010 (Selkies Tokens).

Uses real Stream image with name prefix t007-stream-tokens.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import socket
import subprocess
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from aiohttp import WSMsgType
from wait import poll_until

logger = logging.getLogger("t007_stream_tokens")

# Read immutable image ID from environment
STREAM_IMAGE = os.environ.get(
    "CBROWSER_STREAM_TEST_IMAGE",
    "sha256:d54a03b61f9d156ffff950f7a9a3aa0a00a2666daf27a7d69f3f35698610a726",
)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SelkiesE2ERunner:
    """Manages isolated Stream container running minimal Selkies service."""

    def __init__(
        self,
        master_token: str = "",
        tokens_file: str = "",
        enable_sharing: bool = True,
        enable_collab: bool = False,
        enable_dual_mode: bool = False,
        port: int = 0,
        extra_docker_args: list[str] | None = None,
    ):
        self.master_token = master_token
        self.tokens_file = tokens_file
        self.enable_sharing = enable_sharing
        self.enable_collab = enable_collab
        self.enable_dual_mode = enable_dual_mode
        self.port = port or find_free_port()
        self.container_name = f"t007-stream-tokens-selkies-{secrets.token_hex(4)}"
        self.extra_docker_args = extra_docker_args or []

    async def start(self) -> str:
        py_script = f"""
import os, sys, asyncio
from selkies.settings import settings
from selkies.stream_server import CentralizedStreamServer
from selkies.webrtc_mode import WebRTCService
from selkies.websockets_mode import DataStreamingServer

async def run_server():
    settings.mode = "webrtc"
    settings.port = {self.port}
    settings.addr = "127.0.0.1"
    settings.master_token = {self.master_token!r}
    settings.tokens_file = {self.tokens_file!r}
    settings.enable_basic_auth = (False, True)
    settings.enable_sharing = ({self.enable_sharing}, True)
    settings.enable_collab = ({self.enable_collab}, True)
    settings.enable_dual_mode = ({self.enable_dual_mode}, True)

    server = CentralizedStreamServer(settings)
    server.register_service("webrtc", WebRTCService(server))
    server.register_service("websockets", DataStreamingServer(server))
    await server.switch_to_mode("webrtc")
    await server.start_server()
    print("SERVER_READY", flush=True)
    while True:
        await asyncio.sleep(1)

asyncio.run(run_server())
"""
        cmd = [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            self.container_name,
            "-p",
            f"127.0.0.1:{self.port}:{self.port}",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m",
        ]
        cmd.extend(self.extra_docker_args)
        cmd.extend(
            [
                "--entrypoint",
                "python3",
                STREAM_IMAGE,
                "-c",
                py_script,
            ]
        )

        await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, check=True
        )
        # Bounded wait for SERVER_READY in logs
        async def read_logs() -> str:
            res = await asyncio.to_thread(
                subprocess.run,
                ["docker", "logs", self.container_name],
                capture_output=True,
                text=True,
                check=False,
            )
            return res.stdout

        try:
            await poll_until(
                read_logs,
                lambda logs: "SERVER_READY" in logs,
                timeout=12.0,
                interval=0.2,
                description=f"SERVER_READY in {self.container_name} logs",
            )
        except TimeoutError:
            self.stop()
            raise RuntimeError(f"Container {self.container_name} failed to reach ready")

        return f"http://127.0.0.1:{self.port}"

    def get_logs(self) -> str:
        res = subprocess.run(
            ["docker", "logs", self.container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.stdout + res.stderr

    def stop(self) -> None:
        subprocess.run(
            ["docker", "stop", self.container_name],
            capture_output=True,
            check=False,
        )


@pytest.mark.asyncio
async def test_e2e_ac008_dual_mode_disabled_negative_and_positive() -> None:
    """AC-008: Dual mode is disabled; switching to websockets is rejected."""
    master_token = secrets.token_urlsafe(32)
    runner = SelkiesE2ERunner(
        master_token=master_token,
        enable_dual_mode=False,
    )
    try:
        base_url = await runner.start()
        async with aiohttp.ClientSession() as session:
            # 1. Probe status endpoint: enable_dual_mode must be False
            async with session.get(f"{base_url}/api/status") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["current_mode"] == "webrtc"
                assert data["enable_dual_mode"] is False

            # 2. Negative test: attempt to switch to websockets mode via /api/switch
            headers = {"Authorization": f"Bearer {master_token}"}
            async with session.post(
                f"{base_url}/api/switch",
                headers=headers,
                json={"mode": "websockets"},
            ) as resp:
                # Must be 403 Forbidden
                assert resp.status == 403
                body = await resp.json()
                assert body["status"] == "error"
                assert body["message"] == "Dual streaming mode disabled"

            # 3. Positive test: WebRTC signaling remains functional
            ws_url = base_url.replace("http://", "ws://") + "/api/webrtc/signaling"
            async with session.ws_connect(ws_url) as ws:
                # Reaching signaling validates WebRTC mode
                await ws.send_str("INVALID PROTOCOL TEST")
                msg = await ws.receive()
                # WebSocket connected and handled message
                assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.TEXT)
    finally:
        runner.stop()


@pytest.mark.asyncio
async def test_e2e_ac010_direct_selkies_signaling_token_gates() -> None:
    """AC-010: Direct Selkies signaling rejects missing or wrong tokens with 4001."""
    master_token = secrets.token_urlsafe(32)
    ctrl_token = secrets.token_urlsafe(32)
    viewer_token = secrets.token_urlsafe(32)

    runner = SelkiesE2ERunner(
        master_token=master_token,
        enable_sharing=True,
        enable_collab=False,
        enable_dual_mode=False,
    )
    try:
        base_url = await runner.start()
        ws_url = base_url.replace("http://", "ws://") + "/api/webrtc/signaling"

        async with aiohttp.ClientSession() as session:
            # Provision tokens via master_token Bearer auth
            headers = {"Authorization": f"Bearer {master_token}"}
            payload = {
                ctrl_token: {
                    "role": "controller",
                    "slot": None,
                    "mk_control": False,
                },
                viewer_token: {
                    "role": "viewer",
                    "slot": None,
                    "mk_control": False,
                },
            }
            async with session.post(
                f"{base_url}/api/tokens",
                headers=headers,
                json=payload,
            ) as resp:
                assert resp.status == 200

            # Case A: Missing client_token in HELLO -> Close 4001
            async with session.ws_connect(ws_url) as ws:
                hello_no_tok = {
                    "client_type": "controller",
                    "client_slot": 1,
                    "client_tab_id": "tab-direct-no-tok",
                    "resume_key": "res-direct-no-tok",
                }
                await ws.send_str(f"HELLO client {json.dumps(hello_no_tok)}")
                msg = await ws.receive()
                assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED)
                assert ws.close_code == 4001
                assert msg.extra == "Invalid authentication token"

            # Case B: Wrong client_token in HELLO -> Close 4001
            async with session.ws_connect(ws_url) as ws:
                hello_bad_tok = {
                    "client_type": "controller",
                    "client_slot": 1,
                    "client_token": "wrong-token-abc-xyz",
                    "client_tab_id": "tab-direct-bad-tok",
                    "resume_key": "res-direct-bad-tok",
                }
                await ws.send_str(f"HELLO client {json.dumps(hello_bad_tok)}")
                msg = await ws.receive()
                assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED)
                assert ws.close_code == 4001
                assert msg.extra == "Invalid authentication token"

            # Case C: Valid controller token in HELLO -> Accepted with HELLO server
            async with session.ws_connect(ws_url) as ws:
                hello_ctrl = {
                    "client_type": "controller",
                    "client_slot": 1,
                    "client_token": ctrl_token,
                    "client_tab_id": "tab-direct-ctrl",
                    "resume_key": "res-direct-ctrl",
                }
                await ws.send_str(f"HELLO client {json.dumps(hello_ctrl)}")
                msg = await ws.receive()
                assert msg.type == WSMsgType.TEXT
                assert msg.data.startswith("HELLO")

            # Case D: Valid viewer token claiming controller -> Accepted but coerced
            async with session.ws_connect(ws_url) as ws:
                hello_viewer = {
                    "client_type": "controller",
                    "client_slot": 1,
                    "client_token": viewer_token,
                    "client_tab_id": "tab-direct-viewer",
                    "resume_key": "res-direct-viewer",
                }
                await ws.send_str(f"HELLO client {json.dumps(hello_viewer)}")
                msg = await ws.receive()
                assert msg.type == WSMsgType.TEXT
                assert msg.data.startswith("HELLO")
    finally:
        runner.stop()


@pytest.mark.asyncio
async def test_e2e_ac010_agent_controller_token_injection_and_coexistence() -> None:
    """AC-010: Agent injects token; tabs coexist; reconnects resume."""
    master_token = secrets.token_urlsafe(32)
    ctrl_token = secrets.token_urlsafe(32)

    runner = SelkiesE2ERunner(
        master_token=master_token,
        enable_sharing=True,
        enable_collab=False,
        enable_dual_mode=False,
    )
    try:
        base_url = await runner.start()
        ws_url = base_url.replace("http://", "ws://") + "/api/webrtc/signaling"

        async with aiohttp.ClientSession() as session:
            # Provision controller token
            headers = {"Authorization": f"Bearer {master_token}"}
            payload = {
                ctrl_token: {
                    "role": "controller",
                    "slot": None,
                    "mk_control": False,
                },
            }
            async with session.post(
                f"{base_url}/api/tokens",
                headers=headers,
                json=payload,
            ) as resp:
                assert resp.status == 200

            def agent_forward_hello(raw_client_hello: dict[str, Any]) -> str:
                """Emulates StreamAgent upstream worker HELLO token injection."""
                meta = dict(raw_client_hello)
                if not meta.get("client_token"):
                    meta["client_token"] = ctrl_token
                return f"HELLO client {json.dumps(meta)}"

            # 1. Page Tab 1 connects without token; Agent injects controller token
            ws1 = await session.ws_connect(ws_url)
            h1 = {
                "client_type": "controller",
                "client_slot": 1,
                "client_tab_id": "tab-alpha",
                "resume_key": "resume-key-alpha-123",
            }
            await ws1.send_str(agent_forward_hello(h1))
            r1 = await ws1.receive()
            assert r1.type == WSMsgType.TEXT
            assert r1.data.startswith("HELLO")

            # 2. Tab 2 connects with different tab_id; Agent injects same token
            ws2 = await session.ws_connect(ws_url)
            h2 = {
                "client_type": "controller",
                "client_slot": 1,
                "client_tab_id": "tab-beta",
                "resume_key": "resume-key-beta-456",
            }
            await ws2.send_str(agent_forward_hello(h2))
            r2 = await ws2.receive()
            assert r2.type == WSMsgType.TEXT
            assert r2.data.startswith("HELLO")

            # Both Tab 1 and Tab 2 remain simultaneously open and connected
            assert not ws1.closed
            assert not ws2.closed

            # 3. Tab 1 reconnects using its original resume_key and tab_id
            ws1_reconnect = await session.ws_connect(ws_url)
            h1_reconnect = {
                "client_type": "controller",
                "client_slot": 1,
                "client_tab_id": "tab-alpha",
                "resume_key": "resume-key-alpha-123",
            }
            await ws1_reconnect.send_str(agent_forward_hello(h1_reconnect))
            r1_rec = await ws1_reconnect.receive()
            assert r1_rec.type == WSMsgType.TEXT
            assert r1_rec.data.startswith("HELLO")

            # Old ws1 socket is closed after resume
            old_close = await ws1.receive()
            assert old_close.type in (WSMsgType.CLOSE, WSMsgType.CLOSED)
            # Both new ws1 and ws2 remain active
            assert not ws1_reconnect.closed
            assert not ws2.closed

            # 4. Tab collision: cloned tab with same tab_id but new resume_key
            ws_cloned = await session.ws_connect(ws_url)
            h_cloned = {
                "client_type": "controller",
                "client_slot": 1,
                "client_tab_id": "tab-alpha",
                "resume_key": "resume-key-cloned-789",
            }
            await ws_cloned.send_str(agent_forward_hello(h_cloned))
            r_cloned = await ws_cloned.receive()
            assert r_cloned.type == WSMsgType.TEXT

            # Old ws1_reconnect is superseded
            evict = await ws1_reconnect.receive()
            assert evict.type in (WSMsgType.CLOSE, WSMsgType.CLOSED)
            assert ws1_reconnect.close_code == 4001
            assert evict.extra == "Superseded by a new connection."

            # Tab 2 remains active and unaffected
            assert not ws2.closed

            await ws2.close()
            await ws_cloned.close()

        # 5. Master token leak scan in container logs
        logs = runner.get_logs()
        assert master_token not in logs, "Master token was leaked in container logs"
    finally:
        runner.stop()


@pytest.mark.asyncio
async def test_e2e_ac010_gateway_topology_runtime_in_secure_mode_with_chrome(
    tmp_path: Path,
) -> None:
    from gateway_probe.browser_oracle import browser_eval
    from gateway_probe.topology import GatewayTopologyHarness
    from playwright.async_api import async_playwright

    harness = GatewayTopologyHarness(tmp_path)
    harness.prefix = f"t007-stream-tokens-gw-{secrets.token_hex(4)}"
    try:
        await harness.start()
        profile = await harness.create_and_start_profile("ac010_prof")
        profile_id = profile["profile_id"]
        browser_cname = profile["browser_container"]

        # Verify the per-instance credentials file lives outside the
        # Browser-mounted runtime dir.
        secret_dir = harness.data_dir / "runtime" / ".secrets" / profile_id
        credential_files = sorted(secret_dir.glob("selkies_tokens_*.json"))
        assert len(credential_files) == 1, credential_files
        tokens_path = credential_files[0]
        assert (tokens_path.stat().st_mode & 0o777) == 0o600, "Must be 0600"
        assert not tokens_path.is_relative_to(harness.data_dir / "runtime" / profile_id)

        browser_inspect = harness.docker_client.api.inspect_container(browser_cname)
        mounted_sources = {m["Source"] for m in browser_inspect["Mounts"]}
        assert str(tokens_path) not in mounted_sources
        assert str(tokens_path.parent) not in mounted_sources
        denied = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "exec",
                browser_cname,
                "cat",
                "/run/cbrowser/runtime/selkies_tokens.json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert denied.returncode != 0, "Browser sandbox could read Selkies tokens"
        listing = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", browser_cname, "ls", "-a", "/run/cbrowser/runtime"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert listing.returncode == 0
        assert "selkies_tokens" not in listing.stdout
        tokens_data = json.loads(tokens_path.read_text(encoding="utf-8"))
        master_token = tokens_data["master_token"]
        controller_token = tokens_data["controller_token"]
        assert len(master_token) >= 42
        assert len(controller_token) >= 42

        # Verify remote browser identity
        initial_remote = await asyncio.to_thread(browser_eval, browser_cname, "true")
        assert initial_remote["identity"]["pid"], "Missing browser PID"
        target_id = initial_remote["target_id"]

        async def evaluate_remote(expression: str) -> dict:
            return await asyncio.to_thread(
                browser_eval, browser_cname, expression, target_id
            )

        # Launch headless Chrome
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                channel="chrome",
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--ignore-certificate-errors",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            context = await browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1280, "height": 720},
            )
            console_logs: list[str] = []
            page = await context.new_page()
            page.on("console", lambda m: console_logs.append(f"[{m.type}] {m.text}"))
            page.on("pageerror", lambda e: console_logs.append(f"[error] {e}"))

            # Login
            await page.goto(harness.origin, wait_until="domcontentloaded")
            login_resp = await page.evaluate(
                """async (password) => {
                    const res = await fetch('/api/v1/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({password})
                    });
                    return res.status;
                }""",
                harness.admin_password,
            )
            assert login_resp == 200, "Login failed"

            # Connect to stream
            stream_url = f"{harness.origin}/?profile_id={profile_id}#primary"
            await page.goto(stream_url, wait_until="domcontentloaded")

            # Wait for WebRTC decode
            await poll_until(
                lambda: page.evaluate(
                    "window.__getWebRTCStats ? window.__getWebRTCStats() : null"
                ),
                lambda stats: bool(
                    stats
                    and stats.get("video")
                    and stats["video"].get("framesDecoded", 0) > 0
                ),
                timeout=25.0,
                interval=0.3,
                description="WebRTC video decode",
            )

            # Verify input through overlayInput to remote browser probe_input
            async def prepare_remote_input() -> None:
                await evaluate_remote("""(() => {
                    const input = document.getElementById('probe_input');
                    if (input) {
                        input.value = '';
                        window.remoteEvents = [];
                        input.focus();
                    }
                    return true;
                })()""")

            async def remote_value() -> Any:
                res = await evaluate_remote(
                    "document.getElementById('probe_input') ? "
                    "document.getElementById('probe_input').value : null"
                )
                return res.get("value")

            await prepare_remote_input()
            await page.locator("#overlayInput").focus()
            await page.keyboard.press("Digit1")
            try:
                value = await poll_until(
                    remote_value,
                    lambda current: current == "1",
                    timeout=3.0,
                    interval=0.1,
                    description="remote key input",
                )
            except TimeoutError:
                value = await remote_value()

            assert value == "1", "Key input did not reach remote browser"

            # Check page visible content and responses do not leak master_token
            page_content = await page.content()
            assert master_token not in page_content, "master_token in page HTML"
            logs_str = "\n".join(console_logs)
            assert master_token not in logs_str, "master_token in console logs"

            await browser.close()

        # Scan logs of every real topology container for the master token
        container_names = [
            profile["browser_container"],
            profile["stream_container"],
            harness.gateway_container.name,
            harness.supervisor_container.name,
            harness.api_container.name,
            harness.caddy_container.name,
        ]
        for name in container_names:
            box = harness.docker_client.containers.get(name)
            text = box.logs().decode("utf-8", errors="replace")
            assert master_token not in text, (
                f"master_token leaked in logs of container {name}"
            )
    finally:
        await harness.cleanup()
