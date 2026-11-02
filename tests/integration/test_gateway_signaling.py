"""Integration tests for Gateway agent registration and viewer signaling."""

import asyncio
import json
import secrets
import sys
from pathlib import Path

import aiohttp
import pytest
from cbrowser.stream_agent.protocol import (
    AgentAction,
    AgentRegisterPayload,
    GatewayControlEnvelope,
    GatewayRegisterResponse,
    GatewayTunnelEnvelope,
    ProtocolEnvelope,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gateway_fixtures import GatewayHarness


@pytest.mark.asyncio
async def test_agent_register_rejects_invalid_token(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")

        # Connect with an invalid token
        invalid_token = secrets.token_hex(32)
        url = f"{harness.ws_url}/stream/agent/register"
        headers = {"Authorization": f"Bearer {invalid_token}"}

        async with (
            aiohttp.ClientSession() as session,
            session.ws_connect(url, headers=headers) as ws,
        ):
                payload = AgentRegisterPayload(
                    hostname="host-1",
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    udp_port=30005,
                    selkies_version="2.1.0",
                    runtime_state="ready",
                    config_version=1,
                    turn_host="127.0.0.1",
                    turn_port=3478,
                )
                env = ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    payload=payload.model_dump(),
                )
                await ws.send_str(env.model_dump_json())

                msg = await ws.receive()
                # Must be closed with 1008
                assert msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE)
                assert ws.close_code == 1008
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

        # API states that valid_instance is the currently bound instance
        harness.api_service.set_profile_runtime(profile_id, valid_instance, "running")

        valid_token = harness.agent_credentials.token_for(profile_id, valid_instance)
        stale_token = harness.agent_credentials.token_for(profile_id, stale_instance)

        url = f"{harness.ws_url}/stream/agent/register"

        async with aiohttp.ClientSession() as session:
            # 1. Connect valid agent
            ws_valid = await session.ws_connect(
                url, headers={"Authorization": f"Bearer {valid_token}"}
            )
            reg_payload_valid = AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=valid_instance,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            env_valid = ProtocolEnvelope(
                action=AgentAction.REGISTER,
                profile_id=profile_id,
                runtime_instance_id=valid_instance,
                payload=reg_payload_valid.model_dump(),
            )
            await ws_valid.send_str(env_valid.model_dump_json())

            # Receive ACK
            ack_msg = await ws_valid.receive()
            assert ack_msg.type == aiohttp.WSMsgType.TEXT
            ack = GatewayRegisterResponse.model_validate_json(ack_msg.data)
            assert ack.status == "ok"
            assert ack.profile_id == profile_id

            # Receive RTC_CONFIG control packet
            rtc_ctrl_msg = await ws_valid.receive()
            assert rtc_ctrl_msg.type == aiohttp.WSMsgType.TEXT
            ctrl = GatewayControlEnvelope.model_validate_json(rtc_ctrl_msg.data)
            assert ctrl.action == AgentAction.RTC_CONFIG

            # 2. Stale instance attempts registration
            ws_stale = await session.ws_connect(
                url, headers={"Authorization": f"Bearer {stale_token}"}
            )
            reg_payload_stale = AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=stale_instance,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            env_stale = ProtocolEnvelope(
                action=AgentAction.REGISTER,
                profile_id=profile_id,
                runtime_instance_id=stale_instance,
                payload=reg_payload_stale.model_dump(),
            )
            await ws_stale.send_str(env_stale.model_dump_json())

            stale_resp = await ws_stale.receive()
            assert stale_resp.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSE,
            )
            assert ws_stale.close_code == 1008

            # 3. Verify valid agent is still connected and operational!
            assert not ws_valid.closed

            await ws_valid.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_agent_heartbeat_timeout_eviction(tmp_path: Path) -> None:
    """AC-002: Stream Agent with no heartbeat within timeout is evicted."""
    # Accelerated heartbeat timeout: 1.0s
    harness = GatewayHarness(tmp_path, agent_heartbeat_timeout_sec=1.0)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        agent_token = harness.agent_credentials.token_for(profile_id, instance_id)

        async with aiohttp.ClientSession() as session:
            ws_agent = await session.ws_connect(
                f"{harness.ws_url}/stream/agent/register",
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            reg_payload = AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            await ws_agent.send_str(
                ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    payload=reg_payload.model_dump(),
                ).model_dump_json()
            )
            await ws_agent.receive()  # ACK
            await ws_agent.receive()  # RTC_CONFIG

            # Agent stops sending heartbeats: Gateway must evict it with close 1001.
            close_msg = await asyncio.wait_for(ws_agent.receive(), timeout=3.0)
            assert close_msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE)
            assert ws_agent.close_code == 1001
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_viewer_handshake_rejections(tmp_path: Path) -> None:
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_val = f"sess_{secrets.token_urlsafe(32)}"

        url = f"{harness.ws_url}/stream/{profile_id}/signal"

        async with aiohttp.ClientSession() as session:
            # 1. Wrong Origin -> 403
            try:
                async with session.ws_connect(
                    url,
                    headers={
                        "Origin": "https://malicious.example.com",
                        "Cookie": f"cbrowser_session={cookie_val}",
                    },
                ):
                    pytest.fail("Expected 403 response")
            except aiohttp.WSServerHandshakeError as e:
                assert e.status == 403

            # 2. Missing cookie -> 401
            try:
                async with session.ws_connect(
                    url,
                    headers={"Origin": "https://localhost:8443"},
                ):
                    pytest.fail("Expected 401 response")
            except aiohttp.WSServerHandshakeError as e:
                assert e.status == 401

            # 3. Session authorization rejected by API -> 403
            harness.api_service.set_viewer_auth(
                cookie_val, profile_id, allowed=False, reason="Banned"
            )
            try:
                async with session.ws_connect(
                    url,
                    headers={
                        "Origin": "https://localhost:8443",
                        "Cookie": f"cbrowser_session={cookie_val}",
                    },
                ):
                    pytest.fail("Expected 403 response")
            except aiohttp.WSServerHandshakeError as e:
                assert e.status == 403

            # 4. Profile has no registered Agent -> 503
            harness.api_service.set_viewer_auth(cookie_val, profile_id, allowed=True)
            try:
                async with session.ws_connect(
                    url,
                    headers={
                        "Origin": "https://localhost:8443",
                        "Cookie": f"cbrowser_session={cookie_val}",
                    },
                ):
                    pytest.fail("Expected 503 response")
            except aiohttp.WSServerHandshakeError as e:
                assert e.status == 503

            # 5. Agent registered, but API observed_state is not running -> 503
            harness.api_service.set_profile_runtime(
                profile_id, instance_id, observed_state="starting"
            )
            agent_token = harness.agent_credentials.token_for(profile_id, instance_id)

            ws_agent = await session.ws_connect(
                f"{harness.ws_url}/stream/agent/register",
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            # Register agent with observed_state = "starting"
            reg_payload = AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            await ws_agent.send_str(
                ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    payload=reg_payload.model_dump(),
                ).model_dump_json()
            )
            await ws_agent.receive()  # ACK
            await ws_agent.receive()  # RTC_CONFIG

            try:
                async with session.ws_connect(
                    url,
                    headers={
                        "Origin": "https://localhost:8443",
                        "Cookie": f"cbrowser_session={cookie_val}",
                    },
                ):
                    pytest.fail("Expected 503 response")
            except aiohttp.WSServerHandshakeError as e:
                assert e.status == 503

            await ws_agent.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_two_viewers_independent_tunnels_and_isolation(
    tmp_path: Path,
) -> None:
    """AC-003: Two viewers have independent tunnels; closing one is isolated."""
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_1 = f"sess_1_{secrets.token_urlsafe(32)}"
        cookie_2 = f"sess_2_{secrets.token_urlsafe(32)}"

        harness.api_service.set_profile_runtime(
            profile_id, instance_id, observed_state="running"
        )
        harness.api_service.set_viewer_auth(cookie_1, profile_id, allowed=True)
        harness.api_service.set_viewer_auth(cookie_2, profile_id, allowed=True)

        agent_token = harness.agent_credentials.token_for(profile_id, instance_id)

        async with aiohttp.ClientSession() as session:
            # 1. Register Agent
            ws_agent = await session.ws_connect(
                f"{harness.ws_url}/stream/agent/register",
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            reg_payload = AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            await ws_agent.send_str(
                ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    payload=reg_payload.model_dump(),
                ).model_dump_json()
            )
            ack_msg = await ws_agent.receive()
            ack = GatewayRegisterResponse.model_validate_json(ack_msg.data)
            agent_session_id = ack.agent_session_id
            await ws_agent.receive()  # RTC_CONFIG

            # 2. Connect Viewer 1
            viewer_url = f"{harness.ws_url}/stream/{profile_id}/signal"
            ws_viewer1 = await session.ws_connect(
                viewer_url,
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_1}",
                },
            )

            # Viewer 1 receives rtc_config first frame
            frame1_msg = await ws_viewer1.receive()
            frame1 = json.loads(frame1_msg.data)
            assert frame1.get("cbrowser") == "rtc_config"
            assert "iceServers" in frame1["rtc_config"]

            # Agent receives tunnel open for Viewer 1
            agent_open1_msg = await ws_agent.receive()
            open1 = GatewayTunnelEnvelope.model_validate_json(agent_open1_msg.data)
            assert open1.type == "open"
            conn_id_1 = open1.conn_id

            # 3. Connect Viewer 2
            ws_viewer2 = await session.ws_connect(
                viewer_url,
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_2}",
                },
            )

            # Viewer 2 receives rtc_config first frame
            frame2_msg = await ws_viewer2.receive()
            frame2 = json.loads(frame2_msg.data)
            assert frame2.get("cbrowser") == "rtc_config"

            # Agent receives tunnel open for Viewer 2
            agent_open2_msg = await ws_agent.receive()
            open2 = GatewayTunnelEnvelope.model_validate_json(agent_open2_msg.data)
            assert open2.type == "open"
            conn_id_2 = open2.conn_id

            assert conn_id_1 != conn_id_2

            # 4. Bidirectional message passing for Viewer 1
            await ws_viewer1.send_str("HELLO client 1")
            agent_msg1 = await ws_agent.receive()
            tunnel_msg1 = GatewayTunnelEnvelope.model_validate_json(agent_msg1.data)
            assert tunnel_msg1.conn_id == conn_id_1
            assert tunnel_msg1.data == "HELLO client 1"

            # Agent replies to Viewer 1
            reply1 = GatewayTunnelEnvelope(
                version="v2",
                type="msg",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                agent_session_id=agent_session_id,
                conn_id=conn_id_1,
                data="HELLO server 1",
            )
            await ws_agent.send_str(reply1.model_dump_json())
            v1_reply = await ws_viewer1.receive()
            assert v1_reply.data == "HELLO server 1"

            # 5. Bidirectional message passing for Viewer 2
            await ws_viewer2.send_str("HELLO client 2")
            agent_msg2 = await ws_agent.receive()
            tunnel_msg2 = GatewayTunnelEnvelope.model_validate_json(agent_msg2.data)
            assert tunnel_msg2.conn_id == conn_id_2
            assert tunnel_msg2.data == "HELLO client 2"

            # Agent replies to Viewer 2
            reply2 = GatewayTunnelEnvelope(
                version="v2",
                type="msg",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                agent_session_id=agent_session_id,
                conn_id=conn_id_2,
                data="HELLO server 2",
            )
            await ws_agent.send_str(reply2.model_dump_json())
            v2_reply = await ws_viewer2.receive()
            assert v2_reply.data == "HELLO server 2"

            # 6. Close Viewer 1 -> Viewer 2 MUST remain connected and unaffected!
            await ws_viewer1.close()

            # Agent receives tunnel close for conn_id_1
            agent_close1_msg = await ws_agent.receive()
            close1 = GatewayTunnelEnvelope.model_validate_json(agent_close1_msg.data)
            assert close1.type == "close"
            assert close1.conn_id == conn_id_1

            # Viewer 2 can still communicate freely!
            assert not ws_viewer2.closed
            await ws_viewer2.send_str("HELLO after v1 closed")
            agent_msg3 = await ws_agent.receive()
            tunnel_msg3 = GatewayTunnelEnvelope.model_validate_json(agent_msg3.data)
            assert tunnel_msg3.conn_id == conn_id_2
            assert tunnel_msg3.data == "HELLO after v1 closed"

            await ws_viewer2.close()
            await ws_agent.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_viewer_control_frames_not_forwarded_to_agent_tunnel(
    tmp_path: Path,
) -> None:
    """Control frames containing 'cbrowser' key must not be forwarded as tunnel msg."""
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_val = f"sess_{secrets.token_urlsafe(32)}"

        harness.api_service.set_profile_runtime(
            profile_id, instance_id, observed_state="running"
        )
        harness.api_service.set_viewer_auth(cookie_val, profile_id, allowed=True)

        agent_token = harness.agent_credentials.token_for(profile_id, instance_id)

        async with aiohttp.ClientSession() as session:
            ws_agent = await session.ws_connect(
                f"{harness.ws_url}/stream/agent/register",
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            reg_payload = AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            await ws_agent.send_str(
                ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    payload=reg_payload.model_dump(),
                ).model_dump_json()
            )
            await ws_agent.receive()  # ACK
            await ws_agent.receive()  # RTC_CONFIG

            ws_viewer = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_id}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_val}",
                },
            )
            await ws_viewer.receive()  # rtc_config
            await ws_agent.receive()  # tunnel open

            # Viewer sends activity control frame
            activity_frame = {"cbrowser": "activity", "visible": True, "active": True}
            await ws_viewer.send_str(json.dumps(activity_frame))

            # Viewer then sends normal Selkies message
            await ws_viewer.send_str("REAL_SIGNALING_MSG")

            # Agent receives REAL_SIGNALING_MSG tunnel msg (not activity frame)
            agent_msg = await ws_agent.receive()
            data = json.loads(agent_msg.data)
            if "action" in data and data["action"] == "visibility_update":
                # Control packet if visibility changed, then tunnel msg
                agent_msg = await ws_agent.receive()
                data = json.loads(agent_msg.data)

            assert data.get("type") == "msg"
            assert data.get("data") == "REAL_SIGNALING_MSG"

            await ws_viewer.close()
            await ws_agent.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_agent_packet_identity_validation_and_cross_profile_isolation(
    tmp_path: Path,
) -> None:
    """AC-002: Agent回传包身份核对与跨Profile/Viewer隔离。

    Agent A 伪造发往 Profile B Viewer 的 msg，B 的 Viewer 收不到。
    """
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_a = f"prof_a_{secrets.token_hex(4)}"
        profile_b = f"prof_b_{secrets.token_hex(4)}"
        inst_a = f"inst_a_{secrets.token_hex(4)}"
        inst_b = f"inst_b_{secrets.token_hex(4)}"
        cookie_a = f"sess_a_{secrets.token_urlsafe(32)}"
        cookie_b = f"sess_b_{secrets.token_urlsafe(32)}"

        harness.api_service.set_profile_runtime(profile_a, inst_a, "running")
        harness.api_service.set_profile_runtime(profile_b, inst_b, "running")
        harness.api_service.set_viewer_auth(cookie_a, profile_a, allowed=True)
        harness.api_service.set_viewer_auth(cookie_b, profile_b, allowed=True)

        token_a = harness.agent_credentials.token_for(profile_a, inst_a)
        token_b = harness.agent_credentials.token_for(profile_b, inst_b)

        async with aiohttp.ClientSession() as session:
            # 1. Connect and register Agent A
            ws_agent_a = await session.ws_connect(
                f"{harness.ws_url}/stream/agent/register",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            reg_a = AgentRegisterPayload(
                hostname="host-a",
                profile_id=profile_a,
                runtime_instance_id=inst_a,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            await ws_agent_a.send_str(
                ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_a,
                    runtime_instance_id=inst_a,
                    payload=reg_a.model_dump(),
                ).model_dump_json()
            )
            ack_a_raw = await ws_agent_a.receive()
            ack_a = GatewayRegisterResponse.model_validate_json(ack_a_raw.data)
            session_a = ack_a.agent_session_id
            await ws_agent_a.receive()  # rtc_config

            # 2. Connect and register Agent B
            ws_agent_b = await session.ws_connect(
                f"{harness.ws_url}/stream/agent/register",
                headers={"Authorization": f"Bearer {token_b}"},
            )
            reg_b = AgentRegisterPayload(
                hostname="host-b",
                profile_id=profile_b,
                runtime_instance_id=inst_b,
                udp_port=30006,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            await ws_agent_b.send_str(
                ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_b,
                    runtime_instance_id=inst_b,
                    payload=reg_b.model_dump(),
                ).model_dump_json()
            )
            ack_b_raw = await ws_agent_b.receive()
            ack_b = GatewayRegisterResponse.model_validate_json(ack_b_raw.data)
            session_b = ack_b.agent_session_id
            await ws_agent_b.receive()  # rtc_config

            # 3. Connect Viewer A
            ws_viewer_a = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_a}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_a}",
                },
            )
            await ws_viewer_a.receive()  # rtc_config
            open_a_raw = await ws_agent_a.receive()  # tunnel open
            assert json.loads(open_a_raw.data)["conn_id"]

            # 4. Connect Viewer B
            ws_viewer_b = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_b}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_b}",
                },
            )
            await ws_viewer_b.receive()  # rtc_config
            open_b_raw = await ws_agent_b.receive()  # tunnel open
            conn_id_b = json.loads(open_b_raw.data)["conn_id"]

            # 5. Attack test 1: Agent A sends forged msg directly to Viewer B
            # using B's conn_id and B's identity
            attack_1 = GatewayTunnelEnvelope(
                version="v2",
                type="msg",
                profile_id=profile_b,
                runtime_instance_id=inst_b,
                agent_session_id=session_b,
                conn_id=conn_id_b,
                data="FORGED_BY_AGENT_A_WITH_IDENTITY_B",
            )
            await ws_agent_a.send_str(attack_1.model_dump_json())

            # 6. Attack test 2: Agent A sends forged msg to Viewer B
            # using B's conn_id but A's own identity
            attack_2 = GatewayTunnelEnvelope(
                version="v2",
                type="msg",
                profile_id=profile_a,
                runtime_instance_id=inst_a,
                agent_session_id=session_a,
                conn_id=conn_id_b,
                data="FORGED_BY_AGENT_A_WITH_IDENTITY_A",
            )
            await ws_agent_a.send_str(attack_2.model_dump_json())

            # 7. Attack test 3: Agent A sends forged action packet
            attack_3 = ProtocolEnvelope(
                action=AgentAction.HEARTBEAT,
                profile_id=profile_b,
                runtime_instance_id=inst_b,
                agent_session_id=session_b,
                payload={"runtime_state": "ready", "viewer_count": 0},
            )
            await ws_agent_a.send_str(attack_3.model_dump_json())

            # 8. Legitimate message from Agent B to Viewer B
            legit_b = GatewayTunnelEnvelope(
                version="v2",
                type="msg",
                profile_id=profile_b,
                runtime_instance_id=inst_b,
                agent_session_id=session_b,
                conn_id=conn_id_b,
                data="LEGIT_FROM_AGENT_B",
            )
            await ws_agent_b.send_str(legit_b.model_dump_json())

            # Viewer B should receive ONLY LEGIT_FROM_AGENT_B, NOT attack_1 or attack_2!
            msg_b = await asyncio.wait_for(ws_viewer_b.receive(), timeout=2.0)
            assert msg_b.type == aiohttp.WSMsgType.TEXT
            assert msg_b.data == "LEGIT_FROM_AGENT_B"

            # Check that no other message arrived at Viewer B
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(ws_viewer_b.receive(), timeout=0.3)
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_agent_session_replacement_closes_old_viewers_and_preserves_new(
    tmp_path: Path,
) -> None:
    """AC-003: 会话替换关闭旧 Viewer。

    Viewer 连上后同实例 Agent 重新注册，旧 Viewer 被关闭（close 1001），
    新 Viewer 可正常建立并收发，不受影响。
    """
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

        agent_token = harness.agent_credentials.token_for(profile_id, instance_id)

        async with aiohttp.ClientSession() as session:
            # 1. Connect Agent Session 1
            ws_agent_1 = await session.ws_connect(
                f"{harness.ws_url}/stream/agent/register",
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            reg_1 = AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            await ws_agent_1.send_str(
                ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    payload=reg_1.model_dump(),
                ).model_dump_json()
            )
            ack_1 = GatewayRegisterResponse.model_validate_json(
                (await ws_agent_1.receive()).data
            )
            assert ack_1.status == "ok"
            sess_1 = ack_1.agent_session_id
            await ws_agent_1.receive()  # rtc_config

            # 2. Connect Viewer 1 (bound to Session 1)
            ws_viewer_1 = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_id}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_v1}",
                },
            )
            await ws_viewer_1.receive()  # rtc_config
            open_1 = json.loads((await ws_agent_1.receive()).data)
            conn_id_1 = open_1["conn_id"]

            # 3. Agent reconnects / replaces with new registration for same instance
            ws_agent_2 = await session.ws_connect(
                f"{harness.ws_url}/stream/agent/register",
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            reg_2 = AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            await ws_agent_2.send_str(
                ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    payload=reg_2.model_dump(),
                ).model_dump_json()
            )
            ack_2 = GatewayRegisterResponse.model_validate_json(
                (await ws_agent_2.receive()).data
            )
            assert ack_2.status == "ok"
            sess_2 = ack_2.agent_session_id
            assert sess_2 != sess_1
            await ws_agent_2.receive()  # rtc_config

            # 4. Old Viewer 1 MUST be closed with code 1001
            close_v1 = await asyncio.wait_for(ws_viewer_1.receive(), timeout=2.0)
            assert close_v1.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE)
            assert close_v1.data == 1001

            # 5. Connect new Viewer 2 (bound to Session 2)
            ws_viewer_2 = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_id}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_v2}",
                },
            )
            await ws_viewer_2.receive()  # rtc_config
            open_2 = json.loads((await ws_agent_2.receive()).data)
            conn_id_2 = open_2["conn_id"]
            assert conn_id_2 != conn_id_1

            # 6. Bi-directional communication between Viewer 2 and Agent 2 works
            await ws_viewer_2.send_str("MSG_FROM_V2")
            agent_2_in = await asyncio.wait_for(ws_agent_2.receive(), timeout=2.0)
            agent_2_data = json.loads(agent_2_in.data)
            assert agent_2_data["type"] == "msg"
            assert agent_2_data["conn_id"] == conn_id_2
            assert agent_2_data["data"] == "MSG_FROM_V2"

            await ws_agent_2.send_str(
                GatewayTunnelEnvelope(
                    version="v2",
                    type="msg",
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    agent_session_id=sess_2,
                    conn_id=conn_id_2,
                    data="REPLY_FROM_A2",
                ).model_dump_json()
            )
            v2_in = await asyncio.wait_for(ws_viewer_2.receive(), timeout=2.0)
            assert v2_in.type == aiohttp.WSMsgType.TEXT
            assert v2_in.data == "REPLY_FROM_A2"

            # Viewer 2 is still alive and not closed
            assert not ws_viewer_2.closed
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_viewer_restart_answer_error_logs_type_only_and_not_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-005: Viewer 控制帧处理中的异常记录 warning（仅异常类型）。

    控制帧不转发给 Agent。
    """
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_val = f"sess_{secrets.token_urlsafe(32)}"

        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        harness.api_service.set_viewer_auth(cookie_val, profile_id, allowed=True)
        agent_token = harness.agent_credentials.token_for(profile_id, instance_id)

        async with aiohttp.ClientSession() as session:
            ws_agent = await session.ws_connect(
                f"{harness.ws_url}/stream/agent/register",
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            reg_payload = AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            )
            await ws_agent.send_str(
                ProtocolEnvelope(
                    action=AgentAction.REGISTER,
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    payload=reg_payload.model_dump(),
                ).model_dump_json()
            )
            await ws_agent.receive()  # ACK
            await ws_agent.receive()  # RTC_CONFIG

            ws_viewer = await session.ws_connect(
                f"{harness.ws_url}/stream/{profile_id}/signal",
                headers={
                    "Origin": "https://localhost:8443",
                    "Cookie": f"cbrowser_session={cookie_val}",
                },
            )
            await ws_viewer.receive()  # rtc_config
            open_msg = await ws_agent.receive()  # tunnel open
            assert json.loads(open_msg.data)["type"] == "open"

            # The only viewer control frame left is ice_restart_answer (plan 9.3)
            from cbrowser.gateway.rotation import RotationCoordinator

            def faulty_restart_answer(*args, **kwargs):
                raise ValueError("Simulated failure with secret")

            monkeypatch.setattr(
                RotationCoordinator,
                "handle_viewer_restart_answer",
                faulty_restart_answer,
            )

            import logging

            caplog.set_level(logging.WARNING, logger="cbrowser.gateway.server")

            control_frame = {
                "cbrowser": "ice_restart_answer",
                "generation": 2,
                "sdp": "v=0 secret",
            }
            await ws_viewer.send_str(json.dumps(control_frame))

            # Send subsequent regular signaling message
            await ws_viewer.send_str("LEGIT_SIGNALING_AFTER_ERROR")

            # Agent must receive ONLY LEGIT_SIGNALING_AFTER_ERROR, NOT control_frame!
            agent_msg = await asyncio.wait_for(ws_agent.receive(), timeout=2.0)
            agent_data = json.loads(agent_msg.data)
            assert agent_data["type"] == "msg"
            assert agent_data["data"] == "LEGIT_SIGNALING_AFTER_ERROR"

            # Verify warning was logged with exception type ValueError
            warning_records = [
                r
                for r in caplog.records
                if r.levelno == logging.WARNING and "ValueError" in r.message
            ]
            assert len(warning_records) >= 1, "Expected warning ValueError"
            # Verify no sensitive exception message or payload logged
            for r in warning_records:
                assert "Simulated failure" not in r.message
                assert "secret" not in r.message
                assert "v=0" not in r.message
    finally:
        await harness.stop()
