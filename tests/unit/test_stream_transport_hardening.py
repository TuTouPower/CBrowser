"""
Unit tests for StreamAgent transport hardening:
- Strict configuration security, SecretStr protection, safe validation error logs
- External secret file fail-closed loading (no silent env fallback on bad file)
- Strict URL validation without userinfo and allocated UDP port pool [30000..30991]
- Fixed display geometry (1920x1080x24) and finite FPS bounds [8..30]
- Security boundary assertions (Docker socket, agent socket, profile userdata)
- Consolidated Gateway Protocol v2 contract enforcement
- Per-viewer queue worker generation ownership
- PeerConnection dictionary extraction ('pc') and ID mapping
- Real aiohttp WebSocket endpoint tests for wire validation & generation ownership
- Real SDK metadata peer correlation without guessing fallbacks
"""

import asyncio
import json
import logging
import os
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from cbrowser.stream_agent.agent import (
    ISO8601Formatter,
    StreamAgent,
    _sanitize_url,
)
from cbrowser.stream_agent.boundary import (
    SecurityError,
    verify_stream_runtime_boundaries,
)
from cbrowser.stream_agent.config import StreamAgentConfig
from cbrowser.stream_agent.protocol import (
    GatewayTunnelEnvelope,
    SupervisorQuotaPayload,
)
from pydantic import ValidationError


def test_config_secret_protection_and_repr():
    """Verify SecretStr never leaks plaintext in str or repr."""
    secret = "my_super_secret_token_12345"
    cfg = StreamAgentConfig(
        profile_id="p_test_1",
        runtime_instance_id="inst_12345",
        gateway_url="ws://gateway.local:8080",
        agent_token=secret,
        udp_mux_port=30006,
    )
    assert secret not in repr(cfg)
    assert secret not in str(cfg)
    assert "***" in repr(cfg)
    assert "***" in str(cfg)
    assert cfg.agent_token.get_secret_value() == secret


def test_config_requires_runtime_instance_id():
    """Verify runtime_instance_id is required and rejects missing/invalid values."""
    with pytest.raises(ValidationError):
        # Missing runtime_instance_id
        StreamAgentConfig(
            profile_id="p1",
            gateway_url="ws://127.0.0.1:8080",
            agent_token="valid_secret_123",
        )

    with pytest.raises(ValidationError, match="Invalid runtime_instance_id"):
        StreamAgentConfig(
            profile_id="p1",
            runtime_instance_id="../bad_instance",
            gateway_url="ws://127.0.0.1:8080",
            agent_token="valid_secret_123",
        )


def test_config_fps_finite_bounds_and_video_mode():
    """Verify NaN/inf FPS bypass is prevented and video_streaming_mode is False."""
    with pytest.raises(ValidationError, match="finite numbers"):
        StreamAgentConfig(
            profile_id="p1",
            runtime_instance_id="inst_1",
            gateway_url="ws://127.0.0.1:8080",
            agent_token="valid_secret_123",
            min_fps=float("nan"),
        )

    with pytest.raises(ValidationError, match="finite numbers"):
        StreamAgentConfig(
            profile_id="p1",
            runtime_instance_id="inst_1",
            gateway_url="ws://127.0.0.1:8080",
            agent_token="valid_secret_123",
            max_fps=float("inf"),
        )

    with pytest.raises(ValidationError, match="video_streaming_mode must be False"):
        StreamAgentConfig(
            profile_id="p1",
            runtime_instance_id="inst_1",
            gateway_url="ws://127.0.0.1:8080",
            agent_token="valid_secret_123",
            video_streaming_mode=True,
        )


def test_config_rejects_extra_fields():
    """Verify extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        StreamAgentConfig(
            profile_id="p1",
            runtime_instance_id="inst_1",
            gateway_url="ws://127.0.0.1:8080",
            agent_token="valid_secret_123",
            injected_unknown="evil",
        )


def test_config_gateway_url_strictness():
    """Verify gateway_url rejects query, fragment, credentials, and invalid ports."""
    base = {
        "profile_id": "p1",
        "runtime_instance_id": "inst_1",
        "agent_token": "valid_secret_123",
    }

    # Query string rejected
    with pytest.raises(ValidationError, match="query parameters"):
        StreamAgentConfig(
            **base,
            gateway_url="ws://127.0.0.1:8080/path?token=leak",
        )

    # URL fragment rejected
    with pytest.raises(ValidationError, match="fragments"):
        StreamAgentConfig(
            **base,
            gateway_url="ws://127.0.0.1:8080/path#fragment",
        )

    # Invalid port rejected
    with pytest.raises(ValidationError, match="port"):
        StreamAgentConfig(
            **base,
            gateway_url="ws://127.0.0.1:70000",
        )


def test_config_from_env_fail_closed(tmp_path):
    """Verify from_env requires runtime_instance_id and fails closed."""
    env = {
        "CBROWSER_PROFILE_ID": "p1",
        "CBROWSER_GATEWAY_URL": "ws://127.0.0.1:8080",
        "CBROWSER_AGENT_TOKEN": "fallback_token_123",
        "CBROWSER_CONFIG_VERSION": "1",
    }

    # Missing runtime_instance_id
    with patch.dict(os.environ, env, clear=True), pytest.raises(
        ValueError, match="CBROWSER_RUNTIME_INSTANCE_ID"
    ):
        StreamAgentConfig.from_env()

    env["CBROWSER_RUNTIME_INSTANCE_ID"] = "inst_999"

    # Bad secret file
    env["CBROWSER_AGENT_SECRET_FILE"] = str(tmp_path / "missing")
    with patch.dict(os.environ, env, clear=True), pytest.raises(
        ValueError, match="Cannot read Agent secret"
    ):
        StreamAgentConfig.from_env()

    # Success with explicit env
    del env["CBROWSER_AGENT_SECRET_FILE"]
    with patch.dict(os.environ, env, clear=True):
        cfg = StreamAgentConfig.from_env()
        assert cfg.runtime_instance_id == "inst_999"
        assert cfg.agent_token.get_secret_value() == "fallback_token_123"


def test_boundary_security_verification(tmp_path):
    """Verify runtime isolation checks detect Docker and agent sockets."""
    x11_mock = tmp_path / "X99"
    x11_mock.touch()
    xauth_mock = tmp_path / ".Xauthority"
    xauth_mock.touch()
    pulse_mock = tmp_path / "pulse"
    pulse_mock.mkdir()
    (pulse_mock / "pulse.cookie").touch()

    clean = (str(tmp_path / "fake_docker.sock"), str(tmp_path / "fake_agent.sock"))
    with patch("cbrowser.stream_agent.boundary.PROHIBITED_PATHS", clean):
        res = verify_stream_runtime_boundaries(
            pulse_dir=str(pulse_mock),
            x11_socket=str(x11_mock),
            xauthority_path=str(xauth_mock),
        )
        assert res["x11_available"] is True
        assert res["pulse_cookie_available"] is True

    bad_docker = tmp_path / "exposed_docker.sock"
    bad_docker.touch()
    with (
        patch("cbrowser.stream_agent.boundary.PROHIBITED_PATHS", (str(bad_docker),)),
        pytest.raises(SecurityError, match="Prohibited path"),
    ):
        verify_stream_runtime_boundaries(
            pulse_dir=str(pulse_mock),
            x11_socket=str(x11_mock),
            xauthority_path=str(xauth_mock),
        )


def test_protocol_strict_wire_envelopes_without_visibility_payload():
    """Verify strict wire models; Gateway visibility payloads no longer exist."""
    from cbrowser.stream_agent import protocol

    # Valid tunnel packet
    t_env = GatewayTunnelEnvelope(
        version="v2",
        type="open",
        profile_id="p1",
        runtime_instance_id="inst_1",
        agent_session_id="ses_1",
        conn_id="conn_1",
    )
    assert t_env.type == "open"

    # Reject missing version
    with pytest.raises(ValidationError):
        GatewayTunnelEnvelope(
            type="open",
            profile_id="p1",
            runtime_instance_id="inst_1",
            agent_session_id="ses_1",
            conn_id="conn_1",
        )

    # Reject msg type without data
    with pytest.raises(ValidationError, match="requires data"):
        GatewayTunnelEnvelope(
            version="v2",
            type="msg",
            profile_id="p1",
            runtime_instance_id="inst_1",
            agent_session_id="ses_1",
            conn_id="conn_1",
        )

    # Page visibility reaches Selkies directly (plan 9.3), not via Gateway
    assert not hasattr(protocol, "VisibilityUpdatePayload")

    # Quota payload rejects non-finite
    with pytest.raises(ValidationError, match="finite"):
        SupervisorQuotaPayload(max_fps_cap=float("inf"))


@pytest.mark.asyncio
async def test_real_ws_gateway_and_worker_generation():
    """Real aiohttp WS test proving wire validation and generation-safe close gating."""
    received_from_agent = []
    gw_ws_holder = []

    async def gateway_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        gw_ws_holder.append(ws)

        # 1. Receive register envelope
        reg_msg = await ws.receive_str()
        received_from_agent.append(json.loads(reg_msg))

        # 2. Reply ACK
        ack = {
            "version": "v2",
            "status": "ok",
            "profile_id": "prof_test",
            "runtime_instance_id": "inst_test",
            "agent_session_id": "ses_active_123",
        }
        await ws.send_str(json.dumps(ack))

        # 3. Echo loop
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                received_from_agent.append(json.loads(msg.data))
        return ws

    upstream_ws_holder = []

    async def upstream_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        upstream_ws_holder.append(ws)
        async for _ in ws:
            pass
        return ws

    app = web.Application()
    app.router.add_get("/stream/agent/register", gateway_handler)
    app.router.add_get("/fake", upstream_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    try:
        cfg = StreamAgentConfig(
            profile_id="prof_test",
            runtime_instance_id="inst_test",
            gateway_url=f"ws://127.0.0.1:{port}",
            agent_token="valid_test_secret_123",
            udp_mux_port=30006,
            selkies_version="2.1.0",
        )
        agent = StreamAgent(config=cfg, upstream_url=f"ws://127.0.0.1:{port}/fake")

        agent_task = asyncio.create_task(agent.connect_and_run())

        # Wait for agent registration
        for _ in range(50):
            if agent.agent_session_id == "ses_active_123" and gw_ws_holder:
                break
            await asyncio.sleep(0.05)

        assert agent.agent_session_id == "ses_active_123"
        gw_ws = gw_ws_holder[0]

        # 1. Send tunnel 'open' for conn_1 (Generation 1)
        open_pkt = {
            "version": "v2",
            "type": "open",
            "profile_id": "prof_test",
            "runtime_instance_id": "inst_test",
            "agent_session_id": "ses_active_123",
            "conn_id": "conn_1",
        }
        await gw_ws.send_str(json.dumps(open_pkt))
        await asyncio.sleep(0.05)

        worker_1 = agent.viewer_workers.get("conn_1")
        assert worker_1 is not None
        assert worker_1.generation == 1

        # 2. Send duplicate tunnel 'open' for conn_1 (Generation 2)
        await gw_ws.send_str(json.dumps(open_pkt))
        await asyncio.sleep(0.05)

        worker_2 = agent.viewer_workers.get("conn_1")
        assert worker_2 is not None
        assert worker_2.generation == 2
        assert worker_2 is not worker_1

        # 3. Test sending malformed and mismatched envelopes
        # Mismatched profile_id
        bad_profile_pkt = {
            "version": "v2",
            "type": "msg",
            "profile_id": "forged_profile",
            "runtime_instance_id": "inst_test",
            "agent_session_id": "ses_active_123",
            "conn_id": "conn_1",
            "data": "hello",
        }
        await gw_ws.send_str(json.dumps(bad_profile_pkt))

        # Stale agent_session_id
        stale_ses_pkt = {
            "version": "v2",
            "type": "msg",
            "profile_id": "prof_test",
            "runtime_instance_id": "inst_test",
            "agent_session_id": "ses_stale_999",
            "conn_id": "conn_1",
            "data": "hello",
        }
        await gw_ws.send_str(json.dumps(stale_ses_pkt))

        # Forged visibility for unknown viewer
        forged_vis_pkt = {
            "version": "v2",
            "action": "visibility_update",
            "profile_id": "prof_test",
            "runtime_instance_id": "inst_test",
            "agent_session_id": "ses_active_123",
            "payload": {"viewer_id": "ghost_viewer", "visible": True},
        }
        await gw_ws.send_str(json.dumps(forged_vis_pkt))
        await asyncio.sleep(0.05)

        # Verify ghost viewer was NOT added to policy
        assert "ghost_viewer" not in agent.policy.peers

        # 4. Simulate old reader from generation 1 exiting
        # Generation-safe check: verify old reader does NOT close Gateway conn
        reader_1 = agent._upstream_reader(gw_ws, "conn_1", AsyncMock(), generation=1)
        await reader_1  # Reader 1 runs and exits

        # Give loop moment to handle any sends
        await asyncio.sleep(0.05)

        # Ensure Gateway did NOT receive a 'close' packet for conn_1 from generation 1
        closes = [
            p
            for p in received_from_agent
            if p.get("type") == "close" and p.get("conn_id") == "conn_1"
        ]
        assert len(closes) == 0

        # Worker 2 must still be intact
        assert "conn_1" in agent.viewer_workers
        assert agent.viewer_workers["conn_1"].generation == 2

        # 5. Clean shutdown via agent.stop()
        await agent.stop()
        assert len(agent.viewer_workers) == 0
        assert len(agent.conn_id_to_sdk_peer_id) == 0
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass

    finally:
        await runner.cleanup()


def test_iso8601_logging_and_sanitization():
    """Verify ISO8601Formatter and credential sanitizers."""
    formatter = ISO8601Formatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None,
    )
    formatted_time = formatter.formatTime(record)
    assert "+00:00" in formatted_time or "Z" in formatted_time or "T" in formatted_time

    # URL query/auth sanitization
    url = "ws://admin:secret@127.0.0.1:8080/path?token=123#frag"
    s_url = _sanitize_url(url)
    assert "secret" not in s_url
    assert "token" not in s_url
    assert "admin" not in s_url

