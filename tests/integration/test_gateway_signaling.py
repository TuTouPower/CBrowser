"""Integration tests for Gateway agent registration and viewer signaling."""

import asyncio
import secrets
import sys
from pathlib import Path

import aiohttp
import pytest
from cbrowser.stream_agent.protocol import (
    AgentHeartbeatEnvelope,
    AgentRegisterEnvelope,
    AgentRegisterPayload,
    GatewayRegisterResponse,
    GatewayTunnelEnvelope,
)

from test_gateway_fixtures import GatewayHarness


def _register_payload(profile_id: str, instance_id: str) -> AgentRegisterPayload:
    return AgentRegisterPayload(
        hostname="host-1",
        profile_id=profile_id,
        runtime_instance_id=instance_id,
        udp_port=30005,
        selkies_version="2.1.0",
        runtime_state="ready",
        config_version=1,
    )


async def _register_agent(
    session: aiohttp.ClientSession,
    harness: GatewayHarness,
    profile_id: str,
    instance_id: str,
    token: str | None = None,
) -> tuple[aiohttp.ClientWebSocketResponse, str]:
    ws_agent = await session.ws_connect(
        f"{harness.ws_url}/stream/agent/register?profile_id={profile_id}"
        f"&runtime_instance_id={instance_id}",
        headers={
            "Authorization": "Bearer "
            + (token or harness.agent_credentials.token_for(profile_id, instance_id))
        },
    )
    await ws_agent.send_str(
        AgentRegisterEnvelope(
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            payload=_register_payload(profile_id, instance_id),
        ).model_dump_json()
    )
    ack = GatewayRegisterResponse.model_validate_json((await ws_agent.receive()).data)
    assert ack.status == "ok"
    return ws_agent, ack.agent_session_id


@pytest.mark.asyncio
async def test_agent_register_rejects_invalid_token(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")

        async with aiohttp.ClientSession() as session:
            with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
                await session.ws_connect(
                    f"{harness.ws_url}/stream/agent/register?profile_id={profile_id}"
                    f"&runtime_instance_id={instance_id}",
                    headers={"Authorization": f"Bearer {secrets.token_hex(32)}"},
                )
            assert exc_info.value.status == 401
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_agent_register_stale_instance_rejected_without_affecting_current(
    tmp_path: Path,
) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        valid_instance = f"inst_valid_{secrets.token_hex(4)}"
        stale_instance = f"inst_stale_{secrets.token_hex(4)}"
        harness.api_service.set_profile_runtime(profile_id, valid_instance, "running")

        async with aiohttp.ClientSession() as session:
            ws_valid, _ = await _register_agent(
                session, harness, profile_id, valid_instance
            )
            with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
                await session.ws_connect(
                    f"{harness.ws_url}/stream/agent/register"
                    f"?profile_id={profile_id}"
                    f"&runtime_instance_id={stale_instance}",
                    headers={
                        "Authorization": "Bearer "
                        + harness.agent_credentials.token_for(
                            profile_id, stale_instance
                        )
                    },
                )
            assert exc_info.value.status == 403
            assert not ws_valid.closed
            await ws_valid.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_agent_heartbeat_timeout_eviction(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path, agent_heartbeat_timeout_sec=1.0)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")

        async with aiohttp.ClientSession() as session:
            ws_agent, _ = await _register_agent(
                session, harness, profile_id, instance_id
            )
            close_msg = await asyncio.wait_for(ws_agent.receive(), timeout=3.0)
            assert close_msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSE,
            )
            assert ws_agent.close_code == 1001
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_viewer_handshake_rejections_leave_no_session(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_val = f"sess_{secrets.token_urlsafe(32)}"
        url = f"{harness.ws_url}/stream/{profile_id}/signal"

        async with aiohttp.ClientSession() as session:
            with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
                await session.ws_connect(
                    url,
                    headers={
                        "Origin": "https://malicious.example.com",
                        "Cookie": f"cbrowser_session={cookie_val}",
                    },
                )
            assert exc_info.value.status == 403

            with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
                await session.ws_connect(
                    url, headers={"Origin": "https://localhost:8443"}
                )
            assert exc_info.value.status == 401

            harness.api_service.set_viewer_auth(
                cookie_val, profile_id, allowed=False, reason="Banned"
            )
            with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
                await session.ws_connect(
                    url,
                    headers={
                        "Origin": "https://localhost:8443",
                        "Cookie": f"cbrowser_session={cookie_val}",
                    },
                )
            assert exc_info.value.status == 403

            harness.api_service.set_viewer_auth(cookie_val, profile_id, allowed=True)
            with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
                await session.ws_connect(
                    url,
                    headers={
                        "Origin": "https://localhost:8443",
                        "Cookie": f"cbrowser_session={cookie_val}",
                    },
                )
            assert exc_info.value.status == 503

            harness.api_service.set_profile_runtime(
                profile_id, instance_id, observed_state="starting"
            )
            ws_agent, _ = await _register_agent(
                session, harness, profile_id, instance_id
            )
            with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
                await session.ws_connect(
                    url,
                    headers={
                        "Origin": "https://localhost:8443",
                        "Cookie": f"cbrowser_session={cookie_val}",
                    },
                )
            assert exc_info.value.status == 503
            await ws_agent.close()

            # A ready Profile can still connect and open exactly one tunnel.
            harness.api_service.set_profile_runtime(
                profile_id, instance_id, observed_state="running"
            )
            ws_agent, session_id = await _register_agent(
                session, harness, profile_id, instance_id
            )
            ws_viewer = await session.ws_connect(
                url,
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_val}",
                },
            )
            opened = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent.receive()).data
            )
            assert opened.type == "open"
            assert opened.agent_session_id == session_id
            await ws_viewer.close()
            await ws_agent.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_viewer_authorization_failures_are_rate_limited(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        url = f"{harness.ws_url}/stream/{profile_id}/signal"
        async with aiohttp.ClientSession() as session:
            for _ in range(10):
                with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
                    await session.ws_connect(
                        url, headers={"Origin": "https://localhost:8443"}
                    )
                assert exc_info.value.status == 401
            with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
                await session.ws_connect(
                    url, headers={"Origin": "https://localhost:8443"}
                )
            assert exc_info.value.status == 429
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_two_viewers_independent_tunnels_and_isolation(
    tmp_path: Path,
) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_1 = f"sess_1_{secrets.token_urlsafe(32)}"
        cookie_2 = f"sess_2_{secrets.token_urlsafe(32)}"
        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        harness.api_service.set_viewer_auth(cookie_1, profile_id, allowed=True)
        harness.api_service.set_viewer_auth(cookie_2, profile_id, allowed=True)

        async with aiohttp.ClientSession() as session:
            ws_agent, session_id = await _register_agent(
                session, harness, profile_id, instance_id
            )
            viewer_url = f"{harness.ws_url}/stream/{profile_id}/signal"
            ws_viewer1 = await session.ws_connect(
                viewer_url,
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_1}",
                },
            )
            open1 = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent.receive()).data
            )
            assert open1.type == "open"

            ws_viewer2 = await session.ws_connect(
                viewer_url,
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_2}",
                },
            )
            open2 = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent.receive()).data
            )
            assert open2.type == "open"
            assert open1.conn_id != open2.conn_id

            await ws_viewer1.send_str("HELLO client 1")
            tunnel_msg1 = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent.receive()).data
            )
            assert tunnel_msg1.conn_id == open1.conn_id
            assert tunnel_msg1.data == "HELLO client 1"

            reply1 = GatewayTunnelEnvelope(
                version="v2",
                type="msg",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                agent_session_id=session_id,
                conn_id=open1.conn_id,
                data="HELLO server 1",
            )
            await ws_agent.send_str(reply1.model_dump_json())
            assert (await ws_viewer1.receive()).data == "HELLO server 1"

            await ws_viewer2.send_str("HELLO client 2")
            tunnel_msg2 = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent.receive()).data
            )
            assert tunnel_msg2.conn_id == open2.conn_id
            assert tunnel_msg2.data == "HELLO client 2"

            await ws_viewer1.close()
            closed = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent.receive()).data
            )
            assert closed.type == "close"
            assert closed.conn_id == open1.conn_id

            await ws_viewer2.send_str("STILL_OPEN")
            still = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent.receive()).data
            )
            assert still.conn_id == open2.conn_id
            assert still.data == "STILL_OPEN"
            await ws_viewer2.close()
            await ws_agent.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_agent_identity_isolation_between_profiles(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_a = f"prof_a_{secrets.token_hex(4)}"
        profile_b = f"prof_b_{secrets.token_hex(4)}"
        inst_a = f"inst_a_{secrets.token_hex(4)}"
        inst_b = f"inst_b_{secrets.token_hex(4)}"
        cookie_b = f"sess_b_{secrets.token_urlsafe(32)}"
        for profile, instance in ((profile_a, inst_a), (profile_b, inst_b)):
            harness.api_service.set_profile_runtime(profile, instance, "running")
        harness.api_service.set_viewer_auth(cookie_b, profile_b, allowed=True)

        async with aiohttp.ClientSession() as session:
            ws_agent_a, _ = await _register_agent(
                session, harness, profile_a, inst_a
            )
            ws_agent_b, session_b = await _register_agent(
                session, harness, profile_b, inst_b
            )
            ws_viewer_b = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_b}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_b}",
                },
            )
            opened = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent_b.receive()).data
            )
            assert opened.type == "open"

            for forged in (
                GatewayTunnelEnvelope(
                    version="v2",
                    type="msg",
                    profile_id=profile_b,
                    runtime_instance_id=inst_b,
                    agent_session_id=session_b,
                    conn_id=opened.conn_id,
                    data="FORGED_TUNNEL",
                ),
                GatewayTunnelEnvelope(
                    version="v2",
                    type="msg",
                    profile_id=profile_a,
                    runtime_instance_id=inst_a,
                    agent_session_id=session_b,
                    conn_id=opened.conn_id,
                    data="FORGED_IDENTITY",
                ),
            ):
                await ws_agent_a.send_str(forged.model_dump_json())

            await ws_agent_a.send_str(
                AgentHeartbeatEnvelope(
                    profile_id=profile_b,
                    runtime_instance_id=inst_b,
                    agent_session_id=session_b,
                    payload={
                        "runtime_state": "ready",
                        "viewer_count": 0,
                        "unpaused_video_consumers": 0,
                        "capture_running": False,
                    },
                ).model_dump_json()
            )

            legitimate = GatewayTunnelEnvelope(
                version="v2",
                type="msg",
                profile_id=profile_b,
                runtime_instance_id=inst_b,
                agent_session_id=session_b,
                conn_id=opened.conn_id,
                data="LEGIT",
            )
            await ws_agent_b.send_str(legitimate.model_dump_json())
            assert (await ws_viewer_b.receive()).data == "LEGIT"
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(ws_viewer_b.receive(), timeout=0.3)

            await ws_viewer_b.close()
            await ws_agent_b.close()
            await ws_agent_a.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_agent_replacement_closes_old_viewers(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_v1 = f"sess_v1_{secrets.token_urlsafe(32)}"
        cookie_v2 = f"sess_v2_{secrets.token_urlsafe(32)}"
        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        harness.api_service.set_viewer_auth(cookie_v1, profile_id, allowed=True)
        harness.api_service.set_viewer_auth(cookie_v2, profile_id, allowed=True)

        async with aiohttp.ClientSession() as session:
            ws_agent_1, sess_1 = await _register_agent(
                session, harness, profile_id, instance_id
            )
            ws_viewer_1 = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_id}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_v1}",
                },
            )
            open_1 = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent_1.receive()).data
            )
            assert open_1.type == "open"

            ws_agent_2, sess_2 = await _register_agent(
                session, harness, profile_id, instance_id
            )
            assert sess_2 != sess_1
            close_v1 = await asyncio.wait_for(ws_viewer_1.receive(), timeout=2.0)
            assert close_v1.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSE,
            )

            ws_viewer_2 = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_id}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_v2}",
                },
            )
            open_2 = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent_2.receive()).data
            )
            assert open_2.type == "open"

            await ws_viewer_2.send_str("MSG_FROM_V2")
            agent_in = GatewayTunnelEnvelope.model_validate_json(
                (await ws_agent_2.receive()).data
            )
            assert agent_in.type == "msg"
            assert agent_in.conn_id == open_2.conn_id
            assert agent_in.data == "MSG_FROM_V2"

            await ws_viewer_2.close()
            await ws_agent_2.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_oversized_viewer_frame_is_rejected_at_transport(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie = f"sess_{secrets.token_urlsafe(32)}"
        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        harness.api_service.set_viewer_auth(cookie, profile_id, allowed=True)
        async with aiohttp.ClientSession() as session:
            ws_agent, _ = await _register_agent(
                session, harness, profile_id, instance_id
            )
            ws_viewer = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_id}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie}",
                },
                max_msg_size=8 * 1024 * 1024,
            )
            await ws_agent.receive()  # tunnel open
            rejected = False
            try:
                await ws_viewer.send_str("x" * (7 * 1024 * 1024))
            except (ConnectionError, aiohttp.ClientError):
                rejected = True
            if not rejected:
                closed = await asyncio.wait_for(ws_viewer.receive(), timeout=5.0)
                rejected = closed.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                )
                if closed.type == aiohttp.WSMsgType.CLOSE:
                    assert ws_viewer.close_code == 1009
            assert rejected
            await ws_agent.close()
    finally:
        await harness.stop()
