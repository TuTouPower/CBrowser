"""Integration tests for TURN rotation cycles and ICE restart handshakes."""

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
    ProtocolEnvelope,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gateway_fixtures import GatewayHarness


@pytest.mark.asyncio
async def test_turn_rotation_and_ice_restart_handshake_sequence(
    tmp_path: Path,
) -> None:
    """AC-004: Validates real ICE restart sequence across all actors."""
    # Short cycle: interval 2.0s, lead time 4.0s, lifetime 6.0s
    # When t >= 2.0s, Gen 2 is created and restart triggers immediately.
    harness = GatewayHarness(
        tmp_path, lifetime_sec=6.0, interval_sec=2.0, lead_time_sec=4.0
    )
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_val = f"sess_{secrets.token_urlsafe(32)}"

        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        harness.api_service.set_viewer_auth(cookie_val, profile_id, allowed=True)
        agent_token = harness.agent_credentials.token_for(profile_id, instance_id)

        session = aiohttp.ClientSession()

        # 1. Connect Agent
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
        init_rtc = await ws_agent.receive()  # Gen 1 RTC_CONFIG
        init_ctrl = GatewayControlEnvelope.model_validate_json(init_rtc.data)
        assert init_ctrl.action == AgentAction.RTC_CONFIG
        assert init_ctrl.payload["generation"] == 1

        # 2. Connect Viewer 1
        ws_viewer = await session.ws_connect(
            f"{harness.ws_url}/stream/{profile_id}/signal",
            headers={
                "Origin": "https://localhost:8443",
                "Cookie": f"cbrowser_session={cookie_val}",
            },
        )
        v_frame1 = json.loads((await ws_viewer.receive()).data)
        assert v_frame1["cbrowser"] == "rtc_config"
        assert v_frame1["generation"] == 1

        open_msg = await ws_agent.receive()
        conn_id = json.loads(open_msg.data)["conn_id"]

        # 3. Wait for ICE restart trigger (within ~3s)
        restart_ctrl = None
        for _ in range(30):
            try:
                msg = await asyncio.wait_for(ws_agent.receive(), timeout=0.5)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("action") == "ice_restart":
                        restart_ctrl = GatewayControlEnvelope.model_validate(data)
                        break
            except TimeoutError:
                pass

        assert restart_ctrl is not None, (
            "Gateway did not trigger ICE restart within timeout"
        )
        assert restart_ctrl.action == AgentAction.ICE_RESTART
        assert restart_ctrl.conn_id == conn_id
        assert restart_ctrl.payload["generation"] == 2
        assert "ice_servers" in restart_ctrl.payload

        # 4. Agent responds with ICE_RESTART_OFFER
        offer_sdp = (
            "v=0\r\no=- 12345 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=sendrecv\r\n"
        )
        offer_env = ProtocolEnvelope(
            action=AgentAction.ICE_RESTART_OFFER,
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            agent_session_id=restart_ctrl.agent_session_id,
            conn_id=conn_id,
            payload={"sdp": offer_sdp, "type": "offer", "generation": 2},
        )
        await ws_agent.send_str(offer_env.model_dump_json())

        # 5. Viewer receives ice_restart control frame with client RTC config and offer
        v_restart_msg = await asyncio.wait_for(ws_viewer.receive(), timeout=2.0)
        v_restart_frame = json.loads(v_restart_msg.data)
        assert v_restart_frame.get("cbrowser") == "ice_restart"
        assert v_restart_frame.get("generation") == 2
        assert "rtc_config" in v_restart_frame
        assert v_restart_frame["offer"]["sdp"] == offer_sdp

        # 6. Viewer responds with ice_restart_answer
        answer_sdp = (
            "v=0\r\no=- 54321 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=sendrecv\r\n"
        )
        answer_frame = {
            "cbrowser": "ice_restart_answer",
            "generation": 2,
            "sdp": {"type": "answer", "sdp": answer_sdp},
        }
        await ws_viewer.send_str(json.dumps(answer_frame))

        # 7. Agent receives ICE_RESTART_ANSWER
        agent_ans_msg = await asyncio.wait_for(ws_agent.receive(), timeout=2.0)
        agent_ans_env = GatewayControlEnvelope.model_validate_json(agent_ans_msg.data)
        assert agent_ans_env.action == AgentAction.ICE_RESTART_ANSWER
        assert agent_ans_env.conn_id == conn_id
        assert agent_ans_env.payload["generation"] == 2
        assert agent_ans_env.payload["sdp"] == answer_sdp

        # 8. New viewer connecting now gets Generation 2 directly!
        cookie_2 = f"sess_new_{secrets.token_urlsafe(32)}"
        harness.api_service.set_viewer_auth(cookie_2, profile_id, allowed=True)
        ws_new_viewer = await session.ws_connect(
            f"{harness.ws_url}/stream/{profile_id}/signal",
            headers={
                "Origin": "https://localhost:8443",
                "Cookie": f"cbrowser_session={cookie_2}",
            },
        )
        new_v_frame = json.loads((await ws_new_viewer.receive()).data)
        assert new_v_frame["cbrowser"] == "rtc_config"
        assert new_v_frame["generation"] == 2

        await ws_new_viewer.close()
        await ws_viewer.close()
        await ws_agent.close()
        await session.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_turn_rotation_agent_error_backoff(tmp_path: Path) -> None:
    """When Agent returns ERROR, Gateway records error and backs off safely."""
    harness = GatewayHarness(
        tmp_path, lifetime_sec=5.0, interval_sec=1.5, lead_time_sec=4.0
    )
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_val = f"sess_{secrets.token_urlsafe(32)}"

        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        harness.api_service.set_viewer_auth(cookie_val, profile_id, allowed=True)
        agent_token = harness.agent_credentials.token_for(profile_id, instance_id)

        session = aiohttp.ClientSession()

        # Connect Agent
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

        # Connect Viewer
        ws_viewer = await session.ws_connect(
            f"{harness.ws_url}/stream/{profile_id}/signal",
            headers={
                "Origin": "https://localhost:8443",
                "Cookie": f"cbrowser_session={cookie_val}",
            },
        )
        await ws_viewer.receive()  # rtc_config
        open_msg = await ws_agent.receive()
        conn_id = json.loads(open_msg.data)["conn_id"]

        # Wait for ICE_RESTART
        restart_ctrl = None
        for _ in range(30):
            try:
                msg = await asyncio.wait_for(ws_agent.receive(), timeout=0.5)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("action") == "ice_restart":
                        restart_ctrl = GatewayControlEnvelope.model_validate(data)
                        break
            except TimeoutError:
                pass

        assert restart_ctrl is not None

        # Agent returns ERROR
        err_env = ProtocolEnvelope(
            action=AgentAction.ERROR,
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            agent_session_id=restart_ctrl.agent_session_id,
            conn_id=conn_id,
            payload={"error": "peer_connection_failed"},
        )
        await ws_agent.send_str(err_env.model_dump_json())

        # Gateway handles error gracefully without unhandled exceptions
        await asyncio.sleep(1.0)
        assert not ws_agent.closed
        assert not ws_viewer.closed

        await ws_viewer.close()
        await ws_agent.close()
        await session.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_new_generation_syncs_to_agent_and_new_viewer(tmp_path: Path) -> None:
    """AC-004: 生成新 generation 时立即向 Agent 发送 rtc_config。

    随后新 Viewer 首帧也是第 2 代。
    """
    # Short cycle: interval=1.0s, lead_time=5.0s, lifetime=10.0s
    harness = GatewayHarness(
        tmp_path, lifetime_sec=10.0, interval_sec=1.0, lead_time_sec=5.0
    )
    await harness.start()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie_val = f"sess_{secrets.token_urlsafe(32)}"

        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        harness.api_service.set_viewer_auth(cookie_val, profile_id, allowed=True)
        agent_token = harness.agent_credentials.token_for(profile_id, instance_id)

        session = aiohttp.ClientSession()

        # 1. Connect and register Agent
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
        init_rtc = await ws_agent.receive()  # Gen 1 RTC_CONFIG
        init_ctrl = GatewayControlEnvelope.model_validate_json(init_rtc.data)
        assert init_ctrl.action == AgentAction.RTC_CONFIG
        assert init_ctrl.payload["generation"] == 1

        # 2. Wait for background rotation to produce Generation 2 (interval=1.0s)
        # Agent must receive Generation 2 RTC_CONFIG!
        gen2_ctrl = None
        for _ in range(40):
            try:
                msg = await asyncio.wait_for(ws_agent.receive(), timeout=0.2)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if (
                        data.get("action") == "rtc_config"
                        and data.get("payload", {}).get("generation") == 2
                    ):
                        gen2_ctrl = GatewayControlEnvelope.model_validate(data)
                        break
            except TimeoutError:
                pass

        assert gen2_ctrl is not None, "Agent did not receive generation 2 rtc_config"
        assert gen2_ctrl.payload["generation"] == 2
        assert len(gen2_ctrl.payload["ice_servers"]) >= 1

        # 3. Connect a NEW Viewer after Generation 2 is produced
        ws_viewer = await session.ws_connect(
            f"{harness.ws_url}/stream/{profile_id}/signal",
            headers={
                "Origin": "https://localhost:8443",
                "Cookie": f"cbrowser_session={cookie_val}",
            },
        )
        v_frame = json.loads((await ws_viewer.receive()).data)
        assert v_frame["cbrowser"] == "rtc_config"
        # The new Viewer's first frame MUST be Generation 2!
        assert v_frame["generation"] == 2

        await ws_viewer.close()
        await ws_agent.close()
        await session.close()
    finally:
        await harness.stop()


async def _drive_restart_to_answer(
    harness: GatewayHarness, session: aiohttp.ClientSession
) -> dict:
    """Register an Agent and a Viewer, then relay one gen-2 restart up to the answer."""
    profile_id = f"prof_{secrets.token_hex(4)}"
    instance_id = f"inst_{secrets.token_hex(4)}"
    cookie_val = f"sess_{secrets.token_urlsafe(32)}"
    harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
    harness.api_service.set_viewer_auth(cookie_val, profile_id, allowed=True)
    ws_agent = await session.ws_connect(
        f"{harness.ws_url}/stream/agent/register",
        headers={
            "Authorization": "Bearer "
            + harness.agent_credentials.token_for(profile_id, instance_id)
        },
    )
    await ws_agent.send_str(
        ProtocolEnvelope(
            action=AgentAction.REGISTER,
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            payload=AgentRegisterPayload(
                hostname="host-1",
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                udp_port=30005,
                selkies_version="2.1.0",
                runtime_state="ready",
                config_version=1,
                turn_host="127.0.0.1",
                turn_port=3478,
            ).model_dump(),
        ).model_dump_json()
    )
    session_id = json.loads((await ws_agent.receive()).data)["agent_session_id"]
    await ws_agent.receive()  # RTC_CONFIG
    ws_viewer = await session.ws_connect(
        f"{harness.ws_url}/stream/{profile_id}/signal",
        headers={
            "Origin": "https://localhost:8443",
            "Cookie": f"cbrowser_session={cookie_val}",
        },
    )
    await ws_viewer.receive()  # rtc_config
    conn_id = json.loads((await ws_agent.receive()).data)["conn_id"]
    ctx = {
        "profile_id": profile_id,
        "instance_id": instance_id,
        "session_id": session_id,
        "conn_id": conn_id,
        "ws_agent": ws_agent,
        "ws_viewer": ws_viewer,
    }
    assert (await _next_agent_action(ws_agent, "ice_restart", 15.0)) is not None
    await _agent_send(
        ctx, AgentAction.ICE_RESTART_OFFER, {"sdp": "v=0", "type": "offer"}
    )
    frame = json.loads((await asyncio.wait_for(ws_viewer.receive(), 2.0)).data)
    assert frame["cbrowser"] == "ice_restart" and frame["generation"] == 2
    await ws_viewer.send_str(
        json.dumps(
            {
                "cbrowser": "ice_restart_answer",
                "generation": 2,
                "sdp": {"type": "answer", "sdp": "v=0"},
            }
        )
    )
    answer = await _next_agent_action(ws_agent, "ice_restart_answer", 2.0)
    assert answer is not None and answer["payload"]["generation"] == 2
    return ctx


async def _next_agent_action(
    ws_agent: aiohttp.ClientWebSocketResponse, action: str, timeout: float
) -> dict | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            msg = await asyncio.wait_for(
                ws_agent.receive(), timeout=max(0.05, deadline - loop.time())
            )
        except TimeoutError:
            return None
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data.get("action") == action:
                return data
    return None


async def _agent_send(ctx: dict, action: AgentAction, payload: dict) -> None:
    await ctx["ws_agent"].send_str(
        ProtocolEnvelope(
            action=action,
            profile_id=ctx["profile_id"],
            runtime_instance_id=ctx["instance_id"],
            agent_session_id=ctx["session_id"],
            conn_id=ctx["conn_id"],
            payload=payload,
        ).model_dump_json()
    )


def _committed(caplog: pytest.LogCaptureFixture, generation: int) -> bool:
    return any(
        f"Generation {generation} officially committed" in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_generation_commits_only_after_agent_confirms_ice_takeover(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-004: a relayed answer is not a verified restart; the Agent must confirm."""
    import logging

    caplog.set_level(logging.INFO, logger="cbrowser.gateway.rotation")
    harness = GatewayHarness(
        tmp_path, lifetime_sec=30.0, interval_sec=2.0, lead_time_sec=28.0
    )
    await harness.start()
    session = aiohttp.ClientSession()
    try:
        ctx = await _drive_restart_to_answer(harness, session)
        await asyncio.sleep(1.0)
        assert not _committed(caplog, 2), "committed before the Agent confirmed"

        await _agent_send(ctx, AgentAction.ICE_RESTART_COMMITTED, {"generation": 2})
        for _ in range(40):
            if _committed(caplog, 2):
                break
            await asyncio.sleep(0.05)
        assert _committed(caplog, 2)
        # A confirmed connection is not restarted again for the same generation.
        repeat = await _next_agent_action(ctx["ws_agent"], "ice_restart", 1.5)
        assert repeat is None or repeat["payload"]["generation"] != 2
    finally:
        await session.close()
        await harness.stop()


@pytest.mark.asyncio
async def test_agent_error_after_answer_retries_without_commit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-004: an ICE takeover failure reported after the answer is retried."""
    import logging

    caplog.set_level(logging.INFO, logger="cbrowser.gateway.rotation")
    harness = GatewayHarness(
        tmp_path, lifetime_sec=30.0, interval_sec=2.0, lead_time_sec=28.0
    )
    await harness.start()
    session = aiohttp.ClientSession()
    try:
        ctx = await _drive_restart_to_answer(harness, session)
        await _agent_send(
            ctx, AgentAction.ERROR, {"error": "ice_restart_not_committed"}
        )
        retry = await _next_agent_action(ctx["ws_agent"], "ice_restart", 6.0)
        assert retry is not None, "failed takeover was not retried"
        assert retry["payload"]["generation"] == 2
        assert retry["conn_id"] == ctx["conn_id"]
        assert not _committed(caplog, 2)
        assert any(
            "backoff" in r.getMessage() and r.levelname == "WARNING"
            for r in caplog.records
        )
    finally:
        await session.close()
        await harness.stop()


@pytest.mark.asyncio
async def test_gateway_stream_rtc_config_carries_relay_only_mode(
    tmp_path: Path,
) -> None:
    """Gateway passes relay_only boolean flag in stream-side RTC config."""
    # 1. Relay-only mode
    harness_relay = GatewayHarness(
        tmp_path / "relay",
        webrtc_mode="relay-only",
        lifetime_sec=60.0,
        interval_sec=1.5,
        lead_time_sec=58.0,
    )
    await harness_relay.start()
    session = aiohttp.ClientSession()
    try:
        profile_id = f"prof_relay_{secrets.token_hex(4)}"
        instance_id = f"inst_relay_{secrets.token_hex(4)}"
        harness_relay.api_service.set_profile_runtime(
            profile_id, instance_id, "running"
        )
        token = harness_relay.agent_credentials.token_for(profile_id, instance_id)

        ws = await session.ws_connect(
            f"{harness_relay.ws_url}/stream/agent/register",
            headers={"Authorization": f"Bearer {token}"},
        )
        await ws.send_str(
            ProtocolEnvelope(
                action=AgentAction.REGISTER,
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                payload=AgentRegisterPayload(
                    hostname="host-1",
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    udp_port=30005,
                    selkies_version="2.1.0",
                    runtime_state="ready",
                    config_version=1,
                    turn_host="127.0.0.1",
                    turn_port=3478,
                ).model_dump(),
            ).model_dump_json()
        )
        await ws.receive()  # ACK
        init_rtc = await ws.receive()  # Gen 1 RTC_CONFIG
        ctrl1 = GatewayControlEnvelope.model_validate_json(init_rtc.data)
        assert ctrl1.action == AgentAction.RTC_CONFIG
        assert ctrl1.payload.get("relay_only") is True

        # Wait for Gen 2 generation RTC_CONFIG pushed by rotation tick
        gen2_ctrl = None
        for _ in range(30):
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if (
                        data.get("action") == "rtc_config"
                        and data.get("payload", {}).get("generation") == 2
                    ):
                        gen2_ctrl = GatewayControlEnvelope.model_validate(data)
                        break
            except TimeoutError:
                pass

        assert gen2_ctrl is not None, "Gen 2 rtc_config not received"
        assert gen2_ctrl.payload.get("relay_only") is True
        await ws.close()
    finally:
        await session.close()
        await harness_relay.stop()

    # 2. Public mode: relay_only must be False
    harness_pub = GatewayHarness(tmp_path / "pub", webrtc_mode="public")
    await harness_pub.start()
    session_pub = aiohttp.ClientSession()
    try:
        profile_id = f"prof_pub_{secrets.token_hex(4)}"
        instance_id = f"inst_pub_{secrets.token_hex(4)}"
        harness_pub.api_service.set_profile_runtime(profile_id, instance_id, "running")
        token = harness_pub.agent_credentials.token_for(profile_id, instance_id)

        ws_pub = await session_pub.ws_connect(
            f"{harness_pub.ws_url}/stream/agent/register",
            headers={"Authorization": f"Bearer {token}"},
        )
        await ws_pub.send_str(
            ProtocolEnvelope(
                action=AgentAction.REGISTER,
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                payload=AgentRegisterPayload(
                    hostname="host-1",
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    udp_port=30005,
                    selkies_version="2.1.0",
                    runtime_state="ready",
                    config_version=1,
                    turn_host="127.0.0.1",
                    turn_port=3478,
                ).model_dump(),
            ).model_dump_json()
        )
        await ws_pub.receive()  # ACK
        init_rtc_pub = await ws_pub.receive()  # Gen 1 RTC_CONFIG
        ctrl_pub = GatewayControlEnvelope.model_validate_json(init_rtc_pub.data)
        assert ctrl_pub.action == AgentAction.RTC_CONFIG
        assert ctrl_pub.payload.get("relay_only") is False
        await ws_pub.close()
    finally:
        await session_pub.close()
        await harness_pub.stop()
