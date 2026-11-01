"""Unit tests for StreamAgent controller token loading and injection."""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp import web
from cbrowser.stream_agent.agent import StreamAgent
from cbrowser.stream_agent.config import StreamAgentConfig
from cbrowser.stream_agent.policy import LiveCapturePolicyAgent
from cbrowser.stream_agent.protocol import GatewayTunnelEnvelope
from pydantic import SecretStr


def test_stream_agent_config_controller_token_from_credentials_file(
    tmp_path: Path,
) -> None:
    ctrl_token = secrets.token_urlsafe(32)
    master_token = secrets.token_urlsafe(32)
    cred_file = tmp_path / "selkies_credentials.json"
    cred_file.write_text(
        json.dumps(
            {
                "master_token": master_token,
                "controller_token": ctrl_token,
            }
        ),
        encoding="utf-8",
    )

    secret_file = tmp_path / "agent_secret.txt"
    secret_file.write_text("agent_secret_value", encoding="utf-8")

    env = {
        "CBROWSER_PROFILE_ID": "p1",
        "CBROWSER_RUNTIME_INSTANCE_ID": "r1",
        "CBROWSER_GATEWAY_URL": "ws://127.0.0.1:18097",
        "CBROWSER_CONFIG_VERSION": "1",
        "CBROWSER_AGENT_SECRET_FILE": str(secret_file),
        "SELKIES_TURN_HOST": "127.0.0.1",
        "SELKIES_TURN_PORT": "3478",
        "CBROWSER_SELKIES_CREDENTIALS_FILE": str(cred_file),
    }

    import os
    from unittest.mock import patch

    with patch.dict(os.environ, env, clear=True):
        cfg = StreamAgentConfig.from_env()

    assert cfg.controller_token is not None
    assert cfg.controller_token.get_secret_value() == ctrl_token
    # Repr must mask controller token
    repr_str = repr(cfg)
    assert ctrl_token not in repr_str
    assert "controller_token='***'" in repr_str
    # Master token must NOT be present in config attributes or repr
    assert not hasattr(cfg, "master_token")
    assert master_token not in repr_str


def test_stream_agent_config_ignores_controller_token_env_var(tmp_path: Path) -> None:
    ctrl_token = secrets.token_urlsafe(32)
    secret_file = tmp_path / "agent_secret.txt"
    secret_file.write_text("agent_secret_value", encoding="utf-8")

    env = {
        "CBROWSER_PROFILE_ID": "p1",
        "CBROWSER_RUNTIME_INSTANCE_ID": "r1",
        "CBROWSER_GATEWAY_URL": "ws://127.0.0.1:18097",
        "CBROWSER_CONFIG_VERSION": "1",
        "CBROWSER_AGENT_SECRET_FILE": str(secret_file),
        "SELKIES_TURN_HOST": "127.0.0.1",
        "SELKIES_TURN_PORT": "3478",
        "CBROWSER_CONTROLLER_TOKEN": ctrl_token,
    }

    import os
    from unittest.mock import patch

    with patch.dict(os.environ, env, clear=True):
        cfg = StreamAgentConfig.from_env()

    assert cfg.controller_token is None


@pytest.mark.asyncio
async def test_agent_hello_token_injection_preserves_tab_id_and_resume_key(
    tmp_path: Path,
) -> None:
    ctrl_token = secrets.token_urlsafe(32)

    cfg = StreamAgentConfig(
        profile_id="p1",
        runtime_instance_id="r1",
        gateway_url="ws://127.0.0.1:18097",
        agent_token=SecretStr("agent_secret_test"),
        turn_host="127.0.0.1",
        turn_port=3478,
        controller_token=SecretStr(ctrl_token),
    )

    policy = LiveCapturePolicyAgent(min_fps=8.0, max_fps=30.0)

    # Mock loopback Selkies WebSocket server
    received_upstream_messages = []

    async def upstream_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                received_upstream_messages.append(msg.data)
                if msg.data.startswith("HELLO client"):
                    # Reply with HELLO server
                    await ws.send_str('HELLO server {"server_type": "display"}')
        return ws

    app = web.Application()
    app.router.add_get("/upstream/ws", upstream_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()

    agent = StreamAgent(
        config=cfg,
        policy_agent=policy,
        upstream_url=f"ws://127.0.0.1:{port}/upstream/ws",
    )

    # Start per-viewer worker
    conn_id = "test_conn_1"
    queue = asyncio.Queue()
    mock_gw_ws = MagicMock()
    mock_gw_ws.send_str = AsyncMock()

    worker_task = None
    try:
        async with aiohttp.ClientSession() as session:
            worker_task = asyncio.create_task(
                agent._viewer_upstream_worker(
                    session=session,
                    gw_ws=mock_gw_ws,
                    conn_id=conn_id,
                    queue=queue,
                    generation=1,
                )
            )

            # Wait for worker to connect upstream
            for _ in range(50):
                vw = agent.viewer_workers.get(conn_id)
                if vw and vw.upstream_ws:
                    break
                await asyncio.sleep(0.05)

            # Send HELLO client from browser page (no client_token)
            orig_tab_id = "test-tab-id-999"
            orig_resume_key = "resume-key-111222"
            browser_hello = {
                "client_type": "controller",
                "client_slot": 1,
                "client_tab_id": orig_tab_id,
                "resume_key": orig_resume_key,
            }
            envelope = GatewayTunnelEnvelope(
                version="v2",
                profile_id="p1",
                runtime_instance_id="r1",
                agent_session_id="sess_1",
                type="msg",
                conn_id=conn_id,
                data=f"HELLO client {json.dumps(browser_hello)}",
            )
            await queue.put(envelope)

            # Wait for upstream server to receive message
            for _ in range(50):
                if received_upstream_messages:
                    break
                await asyncio.sleep(0.05)

            assert len(received_upstream_messages) == 1
            received_raw = received_upstream_messages[0]
            assert received_raw.startswith("HELLO client ")
            meta_json = received_raw.split(" ", 2)[2]
            meta = json.loads(meta_json)

            # 1. Controller token was injected
            assert meta["client_token"] == ctrl_token
            # 2. client_tab_id and resume_key were untouched
            assert meta["client_tab_id"] == orig_tab_id
            assert meta["resume_key"] == orig_resume_key

            # 3. Simulate reconnection with same resume_key and tab_id
            reconnect_hello = {
                "client_type": "controller",
                "client_slot": 1,
                "client_tab_id": orig_tab_id,
                "resume_key": orig_resume_key,
            }
            await queue.put(
                GatewayTunnelEnvelope(
                    version="v2",
                    profile_id="p1",
                    runtime_instance_id="r1",
                    agent_session_id="sess_1",
                    type="msg",
                    conn_id=conn_id,
                    data=f"HELLO client {json.dumps(reconnect_hello)}",
                )
            )
            for _ in range(50):
                if len(received_upstream_messages) >= 2:
                    break
                await asyncio.sleep(0.05)

            assert len(received_upstream_messages) == 2
            reconnect_raw = received_upstream_messages[1]
            reconnect_meta = json.loads(reconnect_raw.split(" ", 2)[2])
            assert reconnect_meta["client_token"] == ctrl_token
            assert reconnect_meta["client_tab_id"] == orig_tab_id
            assert reconnect_meta["resume_key"] == orig_resume_key

            # Close connection
            await queue.put(
                GatewayTunnelEnvelope(
                    version="v2",
                    profile_id="p1",
                    runtime_instance_id="r1",
                    agent_session_id="sess_1",
                    type="close",
                    conn_id=conn_id,
                )
            )
            await asyncio.wait_for(worker_task, timeout=2.0)
    finally:
        if worker_task and not worker_task.done():
            worker_task.cancel()
        await site.stop()
        await runner.cleanup()


def test_entrypoint_script_ac008_and_ac010_directives() -> None:
    entrypoint_path = Path("config/docker/stream_runtime/entrypoint.sh")
    content = entrypoint_path.read_text(encoding="utf-8")

    # AC-008: Dual mode disabled
    assert "SELKIES_ENABLE_DUAL_MODE=false" in content
    assert "--enable-dual-mode=false" in content

    # AC-008: File transfers disabled (plan 8.1)
    assert "SELKIES_FILE_TRANSFERS=none" in content
    assert "--file-transfers=none" in content

    # AC-010: Master token and tokens file provisioned with 0600
    assert "SELKIES_MASTER_TOKEN" in content
    assert "SELKIES_TOKENS_FILE" in content
    assert "0o600" in content or "0600" in content
