"""Integration tests for Supervisor -> Gateway control RPC."""

import asyncio
import json
import secrets
from pathlib import Path

import aiohttp
import httpx
import pytest
from cbrowser.stream_agent.protocol import (
    AgentAction,
    AgentRegisterEnvelope,
    AgentRegisterPayload,
    GatewayControlEnvelope,
    GatewayTunnelEnvelope,
)
from cbrowser.supervisor.gateway_client import GatewayControlClient

from test_gateway_fixtures import GatewayHarness


async def _register_agent(
    session: aiohttp.ClientSession,
    harness: GatewayHarness,
    profile_id: str,
    instance_id: str,
) -> tuple[aiohttp.ClientWebSocketResponse, str]:
    ws_agent = await session.ws_connect(
        f"{harness.ws_url}/stream/agent/register?profile_id={profile_id}"
        f"&runtime_instance_id={instance_id}",
        headers={
            "Authorization": "Bearer "
            + harness.agent_credentials.token_for(profile_id, instance_id)
        },
    )
    reg_payload = AgentRegisterPayload(
        hostname="host-1",
        profile_id=profile_id,
        runtime_instance_id=instance_id,
        udp_port=30005,
        selkies_version="2.1.0",
        runtime_state="ready",
        config_version=1,    )
    await ws_agent.send_str(
        AgentRegisterEnvelope(
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            payload=reg_payload,
        ).model_dump_json()
    )
    ack = json.loads((await ws_agent.receive()).data)
    return ws_agent, ack["agent_session_id"]


async def _report(
    ws_agent: aiohttp.ClientWebSocketResponse,
    profile_id: str,
    instance_id: str,
    session_id: str,
    payload: dict,
) -> None:
    await ws_agent.send_str(
        json.dumps(
            {
                "version": "v2",
                "action": "heartbeat",
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "agent_session_id": session_id,
                "payload": payload,
            }
        )
    )


async def _visibility_json(
    harness: GatewayHarness, profile_id: str, instance_id: str, expect: dict
) -> dict:
    token = harness.gw_token_file.read_text(encoding="utf-8").strip()
    async with httpx.AsyncClient(base_url=harness.base_url, trust_env=False) as client:
        body: dict = {}
        for _ in range(40):
            response = await client.get(
                f"/gateway/v1/internal/profiles/{profile_id}/visibility",
                headers={"Authorization": f"Bearer {token}"},
                params={"runtime_instance_id": instance_id},
            )
            if response.status_code == 200:
                body = response.json()
                if all(body.get(k) == v for k, v in expect.items()):
                    return body
            await asyncio.sleep(0.05)
        return body


def _beat(unpaused: int, capturing: bool) -> dict:
    return {
        "runtime_state": "ready",
        "viewer_count": 2,
        "unpaused_video_consumers": unpaused,
        "capture_running": capturing,
    }


@pytest.mark.asyncio
async def test_supervisor_control_auth_fence_quota_and_reported_visibility(
    tmp_path: Path,
) -> None:
    """AC-007: visibility endpoint returns only the Agent's last health report."""
    harness = GatewayHarness(tmp_path)
    await harness.start()
    session = aiohttp.ClientSession()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        wrong_instance_id = f"inst_wrong_{secrets.token_hex(4)}"

        invalid_token_file = tmp_path / "invalid_token.txt"
        invalid_token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        invalid_token_file.chmod(0o600)
        client_bad_auth = GatewayControlClient(
            base_url=harness.base_url, token_file=invalid_token_file
        )
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client_bad_auth.has_foreground_viewers(profile_id, instance_id)
        assert exc_info.value.response.status_code == 401
        await client_bad_auth.close()

        client = GatewayControlClient(
            base_url=harness.base_url, token_file=harness.gw_token_file
        )
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.has_foreground_viewers(profile_id, instance_id)
        assert exc_info.value.response.status_code == 503

        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        ws_agent, session_id = await _register_agent(
            session, harness, profile_id, instance_id
        )

        # Registered but not yet reported: unknown, never a guessed False.
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.has_foreground_viewers(profile_id, instance_id)
        assert exc_info.value.response.status_code == 503

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.has_foreground_viewers(profile_id, wrong_instance_id)
        assert exc_info.value.response.status_code == 409
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.set_quota(profile_id, wrong_instance_id, max_fps_cap=15.0)
        assert exc_info.value.response.status_code == 409
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.disconnect_viewers(profile_id, wrong_instance_id)
        assert exc_info.value.response.status_code == 409

        await _report(ws_agent, profile_id, instance_id, session_id, _beat(1, True))
        body = await _visibility_json(
            harness, profile_id, instance_id, {"unpaused_video_consumers": 1}
        )
        assert body == {
            "has_foreground_viewers": True,
            "unpaused_video_consumers": 1,
            "capture_running": True,
        }
        assert await client.has_foreground_viewers(profile_id, instance_id) is True

        await _report(ws_agent, profile_id, instance_id, session_id, _beat(0, False))
        body = await _visibility_json(
            harness, profile_id, instance_id, {"unpaused_video_consumers": 0}
        )
        assert body["capture_running"] is False
        assert await client.has_foreground_viewers(profile_id, instance_id) is False

        # A malformed report neither changes the stored value nor counts as alive.
        await _report(
            ws_agent,
            profile_id,
            instance_id,
            session_id,
            {"runtime_state": "ready", "viewer_count": 2},
        )
        await asyncio.sleep(0.2)
        assert await client.has_foreground_viewers(profile_id, instance_id) is False

        token = harness.gw_token_file.read_text(encoding="utf-8").strip()
        async with httpx.AsyncClient(
            base_url=harness.base_url, trust_env=False
        ) as raw_client:
            rejected = await raw_client.post(
                f"/gateway/v1/internal/profiles/{profile_id}/quota",
                headers={"Authorization": f"Bearer {token}"},
                json={"runtime_instance_id": instance_id, "max_fps_cap": 99},
            )
            assert rejected.status_code == 400
            not_object = await raw_client.post(
                f"/gateway/v1/internal/profiles/{profile_id}/quota",
                headers={"Authorization": f"Bearer {token}"},
                json=["not-an-object"],
            )
            assert not_object.status_code == 400
            bad_disconnect = await raw_client.post(
                f"/gateway/v1/internal/profiles/{profile_id}/disconnect",
                headers={"Authorization": f"Bearer {token}"},
                json="not-an-object",
            )
            assert bad_disconnect.status_code == 400

        await client.set_quota(profile_id, instance_id, max_fps_cap=20.0)
        quota_env = GatewayControlEnvelope.model_validate_json(
            (await ws_agent.receive()).data
        )
        assert quota_env.action == AgentAction.SUPERVISOR_QUOTA
        assert quota_env.payload.max_fps_cap == 20.0

        await client.close()
        await ws_agent.close()
    finally:
        await session.close()
        await harness.stop()


@pytest.mark.asyncio
async def test_supervisor_disconnect_closes_viewers_and_preserves_agent(
    tmp_path: Path,
) -> None:
    harness = GatewayHarness(tmp_path)
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
            f"{harness.ws_url}/stream/agent/register?profile_id={profile_id}"
            f"&runtime_instance_id={instance_id}",
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
        )
        await ws_agent.send_str(
            AgentRegisterEnvelope(
                profile_id=profile_id,
                runtime_instance_id=instance_id,
                payload=reg_payload,
            ).model_dump_json()
        )
        await ws_agent.receive()  # ACK

        # Connect Viewer
        ws_viewer = await session.ws_connect(
            f"{harness.ws_url}/stream/{profile_id}/signal",
            headers={
                "Origin": "https://localhost:8443",
                "Cookie": f"cbrowser_session={cookie_val}",
            },
        )
        await ws_agent.receive()  # tunnel open

        client = GatewayControlClient(
            base_url=harness.base_url, token_file=harness.gw_token_file
        )

        # Disconnect viewers
        await client.disconnect_viewers(profile_id, instance_id)

        # Viewer must receive close
        v_msg = await ws_viewer.receive()
        assert v_msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE)

        # Agent must receive tunnel close packet
        ag_msg = await ws_agent.receive()
        tunnel_close = GatewayTunnelEnvelope.model_validate_json(ag_msg.data)
        assert tunnel_close.type == "close"

        # Agent WS must remain connected and operational!
        assert not ws_agent.closed

        await client.close()
        await ws_agent.close()
        await session.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_viewer_frames_never_change_visibility_or_reach_agent_as_control(
    tmp_path: Path,
) -> None:
    """AC-007: Gateway collects no page visibility/activity and sends no updates."""
    harness = GatewayHarness(tmp_path)
    await harness.start()
    session = aiohttp.ClientSession()
    try:
        profile_id = f"prof_{secrets.token_hex(4)}"
        instance_id = f"inst_{secrets.token_hex(4)}"
        cookie = f"sess_{secrets.token_urlsafe(32)}"
        harness.api_service.set_profile_runtime(profile_id, instance_id, "running")
        harness.api_service.set_viewer_auth(cookie, profile_id, allowed=True)
        ws_agent, session_id = await _register_agent(
            session, harness, profile_id, instance_id
        )
        await _report(ws_agent, profile_id, instance_id, session_id, _beat(0, False))
        await _visibility_json(
            harness, profile_id, instance_id, {"unpaused_video_consumers": 0}
        )

        ws_viewer = await session.ws_connect(
            f"{harness.ws_url}/stream/{profile_id}/signal",
            headers={
                "Origin": "https://localhost:8443",
                "Cookie": f"cbrowser_session={cookie}",
            },
        )
        assert json.loads((await ws_agent.receive()).data)["type"] == "open"

        for frame in (
            {"cbrowser": "activity", "visible": True, "active": True},
            {"cbrowser": "visibility", "visible": True},
        ):
            await ws_viewer.send_str(json.dumps(frame))
        await ws_viewer.send_str("REAL_SIGNALING_MSG")

        # The very next Agent packet is the tunnelled message: no control frame.
        data = json.loads((await asyncio.wait_for(ws_agent.receive(), 2.0)).data)
        assert data["type"] == "msg"
        assert data["data"] == "REAL_SIGNALING_MSG"

        client = GatewayControlClient(
            base_url=harness.base_url, token_file=harness.gw_token_file
        )
        assert await client.has_foreground_viewers(profile_id, instance_id) is False

        # A new registration of another instance does not inherit the old report.
        new_instance = f"inst_{secrets.token_hex(4)}"
        harness.api_service.set_profile_runtime(profile_id, new_instance, "running")
        ws_new, _ = await _register_agent(session, harness, profile_id, new_instance)
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.has_foreground_viewers(profile_id, new_instance)
        assert exc_info.value.response.status_code == 503

        await client.close()
        await ws_viewer.close()
        await ws_new.close()
        await ws_agent.close()
    finally:
        await session.close()
        await harness.stop()
