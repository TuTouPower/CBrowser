"""Stream Gateway application, route handlers, and background tasks."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from aiohttp import WSMsgType, web
from cbrowser.rtc_config.models import RtcScheduleParams
from cbrowser.rtc_config.service import RtcConfigService
from cbrowser.stream_agent.protocol import (
    AgentAction,
    AgentHeartbeatPayload,
    AgentRegisterPayload,
    GatewayControlEnvelope,
    GatewayRegisterResponse,
    GatewayTunnelEnvelope,
    ProtocolEnvelope,
)
from cbrowser.supervisor.agent_credentials import AgentCredentials
from pydantic import ValidationError

from .api_client import GatewayApiClient
from .config import GatewayConfig
from .registry import AgentRegistry, RegisteredAgent
from .rotation import RotationCoordinator

logger = logging.getLogger("cbrowser.gateway.server")


@dataclass
class ViewerEntry:
    conn_id: str
    profile_id: str
    agent_session_id: str
    ws: web.WebSocketResponse


def create_gateway_app(
    config: GatewayConfig,
    api_client: GatewayApiClient | None = None,
) -> web.Application:
    """Builds and configures the aiohttp Gateway web application."""
    app = web.Application()

    credentials = AgentCredentials(config.agent_key_file)
    control_token = (
        config.gateway_token_file.read_text(encoding="utf-8").strip().encode("utf-8")
    )
    api = api_client or GatewayApiClient(config.api_url, config.api_token_file)

    rtc_params = RtcScheduleParams(
        credential_lifetime_sec=config.credential_lifetime_sec,
        generation_interval_sec=config.generation_interval_sec,
        ice_restart_lead_time_sec=config.ice_restart_lead_time_sec,
    )
    rtc_service = RtcConfigService(
        turn_secret_file=config.turn_secret_file,
        turn_public_urls=config.turn_public_urls,
        webrtc_mode=config.webrtc_mode,
        params=rtc_params,
    )

    registry = AgentRegistry()
    viewers: dict[str, ViewerEntry] = {}

    def profile_connections(profile_id: str) -> list[str]:
        return [cid for cid, v in viewers.items() if v.profile_id == profile_id]

    async def close_viewers_for_session(
        session_id: str,
        code: int = 1001,
        message: bytes = b"Stream Agent disconnected",
    ) -> None:
        target_cids = [
            cid for cid, v in list(viewers.items()) if v.agent_session_id == session_id
        ]
        for cid in target_cids:
            v_entry = viewers.pop(cid, None)
            if v_entry:
                if not v_entry.ws.closed:
                    try:
                        await v_entry.ws.close(code=code, message=message)
                    except Exception:
                        pass

    async def send_agent_control(env: GatewayControlEnvelope) -> None:
        agent = registry.get(env.profile_id)
        if agent is not None and not agent.ws.closed:
            await agent.ws.send_str(env.model_dump_json())

    async def send_viewer_control(conn_id: str, frame: dict[str, Any]) -> None:
        viewer_entry = viewers.get(conn_id)
        if viewer_entry is not None:
            if not viewer_entry.ws.closed:
                await viewer_entry.ws.send_str(json.dumps(frame))

    rotation = RotationCoordinator(
        rtc_service=rtc_service,
        send_agent_control=send_agent_control,
        send_viewer_control=send_viewer_control,
        get_active_connections=profile_connections,
        get_agent_info=lambda pid: registry.get(pid),
    )

    # ---------------- Supervisor Auth Helper ----------------
    def _check_supervisor_auth(request: web.Request) -> web.Response | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return web.json_response(
                {"detail": "Missing or invalid Bearer authorization header"},
                status=401,
            )
        provided = auth[len("Bearer ") :].strip().encode("utf-8")
        if not hmac.compare_digest(provided, control_token):
            return web.json_response(
                {"detail": "Unauthorized control token"}, status=401
            )
        return None

    # ---------------- Supervisor Control Routes ----------------
    async def handle_supervisor_visibility(request: web.Request) -> web.Response:
        auth_err = _check_supervisor_auth(request)
        if auth_err:
            return auth_err

        profile_id = request.match_info["profile_id"]
        runtime_instance_id = request.query.get("runtime_instance_id")
        if not runtime_instance_id:
            return web.json_response(
                {"detail": "runtime_instance_id query parameter is required"},
                status=400,
            )

        agent = registry.get(profile_id)
        if agent is None or agent.ws.closed:
            return web.json_response(
                {"detail": f"Agent for profile {profile_id} is unavailable"},
                status=503,
            )
        if agent.instance_id != runtime_instance_id:
            return web.json_response(
                {
                    "detail": (
                        f"Instance fence conflict: active instance is "
                        f"{agent.instance_id}, requested {runtime_instance_id}"
                    )
                },
                status=409,
            )

        # Only the Agent's last health report (Selkies peer state) is returned.
        if agent.unpaused_video_consumers is None or agent.capture_running is None:
            return web.json_response(
                {"detail": f"Agent for profile {profile_id} has not reported yet"},
                status=503,
            )
        return web.json_response(
            {
                "has_foreground_viewers": agent.unpaused_video_consumers > 0,
                "unpaused_video_consumers": agent.unpaused_video_consumers,
                "capture_running": agent.capture_running,
            }
        )

    async def handle_supervisor_quota(request: web.Request) -> web.Response:
        auth_err = _check_supervisor_auth(request)
        if auth_err:
            return auth_err

        profile_id = request.match_info["profile_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON body"}, status=400)

        runtime_instance_id = body.get("runtime_instance_id")
        if not runtime_instance_id:
            return web.json_response(
                {"detail": "runtime_instance_id is required in body"},
                status=400,
            )

        agent = registry.get(profile_id)
        if agent is None or agent.ws.closed:
            return web.json_response(
                {"detail": f"Agent for profile {profile_id} is unavailable"},
                status=503,
            )
        if agent.instance_id != runtime_instance_id:
            return web.json_response(
                {
                    "detail": (
                        f"Instance fence conflict: active instance is "
                        f"{agent.instance_id}, requested {runtime_instance_id}"
                    )
                },
                status=409,
            )

        max_fps_cap = body.get("max_fps_cap")
        env = GatewayControlEnvelope(
            version="v2",
            action=AgentAction.SUPERVISOR_QUOTA,
            profile_id=profile_id,
            runtime_instance_id=agent.instance_id,
            agent_session_id=agent.agent_session_id,
            payload={"max_fps_cap": max_fps_cap},
        )
        await agent.ws.send_str(env.model_dump_json())
        return web.json_response({"status": "ok"})

    async def handle_supervisor_disconnect(request: web.Request) -> web.Response:
        auth_err = _check_supervisor_auth(request)
        if auth_err:
            return auth_err

        profile_id = request.match_info["profile_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON body"}, status=400)

        runtime_instance_id = body.get("runtime_instance_id")
        if not runtime_instance_id:
            return web.json_response(
                {"detail": "runtime_instance_id is required in body"},
                status=400,
            )

        agent = registry.get(profile_id)
        if agent is None or agent.ws.closed:
            return web.json_response(
                {"detail": f"Agent for profile {profile_id} is unavailable"},
                status=503,
            )
        if agent.instance_id != runtime_instance_id:
            return web.json_response(
                {
                    "detail": (
                        f"Instance fence conflict: active instance is "
                        f"{agent.instance_id}, requested {runtime_instance_id}"
                    )
                },
                status=409,
            )

        # Disconnect viewer WebSockets only; do NOT disconnect Agent WS
        for cid in profile_connections(profile_id):
            v_entry = viewers.pop(cid, None)
            if v_entry:
                if not v_entry.ws.closed:
                    await v_entry.ws.close(
                        code=1000, message=b"Supervisor disconnected viewers"
                    )
            # Notify agent of close
            if not agent.ws.closed:
                close_env = GatewayTunnelEnvelope(
                    version="v2",
                    type="close",
                    profile_id=profile_id,
                    runtime_instance_id=agent.instance_id,
                    agent_session_id=agent.agent_session_id,
                    conn_id=cid,
                    code=1000,
                    reason="Supervisor disconnected viewers",
                )
                await agent.ws.send_str(close_env.model_dump_json())

        return web.json_response({"status": "ok"})

    # ---------------- Agent Register Route ----------------
    async def handle_agent_register(request: web.Request) -> web.WebSocketResponse:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return web.Response(status=401, text="Unauthorized Agent")
        raw_token = auth.removeprefix("Bearer ").strip()

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        msg = await ws.receive()
        if msg.type != WSMsgType.TEXT:
            await ws.close(code=1003, message=b"Expected text registration packet")
            return ws

        try:
            reg_raw = json.loads(msg.data)
            envelope = ProtocolEnvelope.model_validate(reg_raw)
            if envelope.action != AgentAction.REGISTER:
                await ws.close(
                    code=1008, message=b"First packet must be register action"
                )
                return ws
            payload = AgentRegisterPayload.model_validate(envelope.payload)
        except (ValidationError, Exception) as e:
            logger.warning("Agent registration payload invalid: %s", type(e).__name__)
            await ws.close(code=1008, message=b"Invalid registration payload")
            return ws

        pid = payload.profile_id
        iid = payload.runtime_instance_id

        # Verify HMAC token
        if not credentials.verify(raw_token, pid, iid):
            await ws.close(code=1008, message=b"Invalid Agent credentials")
            return ws

        # Query internal API for profile runtime binding
        runtime_info = await api.get_profile_runtime(pid)
        if not runtime_info or runtime_info.get("runtime_instance_id") != iid:
            exp_iid = runtime_info.get("runtime_instance_id") if runtime_info else None
            logger.warning(
                "Rejected agent for %s: instance %s not bound (expected %s)",
                pid,
                iid,
                exp_iid,
            )
            # Crucial: Close 1008 and DO NOT overwrite existing registration
            await ws.close(
                code=1008, message=b"Instance not currently bound to profile"
            )
            return ws

        session_id = str(uuid.uuid4())
        agent = RegisteredAgent(
            profile_id=pid,
            instance_id=iid,
            agent_session_id=session_id,
            selkies_version=payload.selkies_version,
            runtime_state=payload.runtime_state,
            udp_port=payload.udp_port,
            config_version=payload.config_version,
            turn_host=payload.turn_host,
            turn_port=payload.turn_port,
            ws=ws,
            last_heartbeat=time.time(),
        )

        old_agent = registry.register(agent)
        if old_agent:
            await close_viewers_for_session(
                old_agent.agent_session_id,
                code=1001,
                message=b"Stream Agent session replaced",
            )
            if not old_agent.ws.closed:
                try:
                    await old_agent.ws.close(
                        code=1000, message=b"Superceded by new registration"
                    )
                except Exception:
                    pass

        # Send ACK
        ack = GatewayRegisterResponse(
            version="v2",
            status="ok",
            profile_id=pid,
            runtime_instance_id=iid,
            agent_session_id=session_id,
        )
        await ws.send_str(ack.model_dump_json())

        # Send Agent RTC_CONFIG
        eff_gen = rotation.get_effective_generation(pid)
        rtc_ctrl = GatewayControlEnvelope(
            version="v2",
            action=AgentAction.RTC_CONFIG,
            profile_id=pid,
            runtime_instance_id=iid,
            agent_session_id=session_id,
            payload=eff_gen.build_stream_rtc_config(
                payload.turn_host, payload.turn_port
            ),
        )
        await ws.send_str(rtc_ctrl.model_dump_json())

        # Pump messages from Agent
        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    try:
                        pkt = json.loads(m.data)
                        if "type" in pkt:
                            # Tunnel envelope
                            tunnel_env = GatewayTunnelEnvelope.model_validate(pkt)
                            if (
                                tunnel_env.profile_id != pid
                                or tunnel_env.runtime_instance_id != iid
                                or tunnel_env.agent_session_id != session_id
                            ):
                                logger.warning(
                                    "Dropped agent tunnel packet: identity mismatch "
                                    "(conn_id=%s, type=%s)",
                                    tunnel_env.conn_id,
                                    tunnel_env.type,
                                )
                                continue

                            conn_id = tunnel_env.conn_id
                            viewer_entry = viewers.get(conn_id)
                            if (
                                viewer_entry is None
                                or viewer_entry.profile_id != pid
                                or viewer_entry.agent_session_id != session_id
                            ):
                                logger.warning(
                                    "Dropped agent tunnel packet: unowned conn_id=%s",
                                    conn_id,
                                )
                                continue

                            v_ws = viewer_entry.ws
                            if tunnel_env.type == "msg" and not v_ws.closed:
                                await v_ws.send_str(tunnel_env.data or "")
                            elif tunnel_env.type == "close" and not v_ws.closed:
                                await v_ws.close(
                                    code=tunnel_env.code or 1000,
                                    message=(
                                        tunnel_env.reason or "Agent closed"
                                    ).encode("utf-8"),
                                )
                                viewers.pop(conn_id, None)
                        elif "action" in pkt:
                            proto_env = ProtocolEnvelope.model_validate(pkt)
                            if (
                                proto_env.profile_id != pid
                                or proto_env.runtime_instance_id != iid
                                or proto_env.agent_session_id != session_id
                            ):
                                logger.warning(
                                    "Dropped agent action packet: identity mismatch "
                                    "(action=%s)",
                                    proto_env.action,
                                )
                                continue

                            if proto_env.action == AgentAction.HEARTBEAT:
                                beat = AgentHeartbeatPayload.model_validate(
                                    proto_env.payload
                                )
                                registry.update_heartbeat(pid, iid)
                                agent.unpaused_video_consumers = (
                                    beat.unpaused_video_consumers
                                )
                                agent.capture_running = beat.capture_running
                            elif proto_env.action == AgentAction.ICE_RESTART_OFFER:
                                rotation.handle_agent_restart_offer(proto_env)
                            elif proto_env.action == AgentAction.ICE_RESTART_COMMITTED:
                                rotation.handle_agent_restart_committed(proto_env)
                            elif proto_env.action == AgentAction.ERROR:
                                rotation.handle_agent_error(proto_env)
                    except Exception as e:
                        logger.warning(
                            "Error processing packet from Agent: %s", type(e).__name__
                        )
                elif m.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        finally:
            await close_viewers_for_session(
                session_id, code=1001, message=b"Stream Agent disconnected"
            )
            registry.remove(pid, ws=ws)

        return ws

    # ---------------- Viewer Signal Route ----------------
    async def handle_viewer_signal(request: web.Request) -> web.WebSocketResponse:
        profile_id = request.match_info["profile_id"]

        # 1. Origin verification
        origin = request.headers.get("Origin", "")
        if origin not in config.allowed_origins:
            return web.Response(status=403, text="Origin not allowed")

        # 2. Session cookie verification
        session_cookie = request.cookies.get("cbrowser_session")
        if not session_cookie:
            return web.Response(
                status=401,
                text="Authentication required: cbrowser_session cookie missing",
            )

        allowed, reason = await api.authorize_viewer(session_cookie, origin, profile_id)
        if not allowed:
            return web.Response(status=403, text=reason or "Viewer unauthorized")

        # 3. Agent readiness & API observed_state check
        agent = registry.get(profile_id)
        if agent is None or agent.ws.closed:
            return web.Response(
                status=503,
                text=f"Profile {profile_id} agent is not currently connected",
            )

        runtime_info = await api.get_profile_runtime(profile_id)
        if not runtime_info or runtime_info.get("observed_state") not in (
            "running",
            "ready",
        ):
            state = runtime_info.get("observed_state") if runtime_info else "none"
            return web.Response(
                status=503,
                text=f"Profile {profile_id} runtime not running (observed: {state})",
            )

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        conn_id = str(uuid.uuid4())
        viewers[conn_id] = ViewerEntry(
            conn_id=conn_id,
            profile_id=profile_id,
            agent_session_id=agent.agent_session_id,
            ws=ws,
        )

        eff_gen = rotation.get_effective_generation(profile_id)

        # 4. First frame to Viewer: rtc_config
        rtc_frame = {
            "cbrowser": "rtc_config",
            "generation": eff_gen.generation,
            "rtc_config": eff_gen.client_rtc_config,
        }
        await ws.send_str(json.dumps(rtc_frame))

        # 5. Open tunnel to Agent
        open_env = GatewayTunnelEnvelope(
            version="v2",
            type="open",
            profile_id=profile_id,
            runtime_instance_id=agent.instance_id,
            agent_session_id=agent.agent_session_id,
            conn_id=conn_id,
        )
        await agent.ws.send_str(open_env.model_dump_json())

        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    text = m.data
                    # Check for cbrowser control frame
                    is_control = False
                    if "cbrowser" in text:
                        try:
                            parsed = json.loads(text)
                            if isinstance(parsed, dict) and "cbrowser" in parsed:
                                is_control = True
                                cb_type = parsed.get("cbrowser")
                                if cb_type == "ice_restart_answer":
                                    rotation.handle_viewer_restart_answer(
                                        conn_id, parsed
                                    )
                        except Exception as e:
                            logger.warning(
                                "Error processing viewer control frame: %s",
                                type(e).__name__,
                            )

                    if not is_control:
                        # Forward to Agent as tunnel msg
                        if not agent.ws.closed:
                            msg_env = GatewayTunnelEnvelope(
                                version="v2",
                                type="msg",
                                profile_id=profile_id,
                                runtime_instance_id=agent.instance_id,
                                agent_session_id=agent.agent_session_id,
                                conn_id=conn_id,
                                data=text,
                            )
                            await agent.ws.send_str(msg_env.model_dump_json())
                elif m.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        finally:
            viewers.pop(conn_id, None)
            if not agent.ws.closed:
                try:
                    close_env = GatewayTunnelEnvelope(
                        version="v2",
                        type="close",
                        profile_id=profile_id,
                        runtime_instance_id=agent.instance_id,
                        agent_session_id=agent.agent_session_id,
                        conn_id=conn_id,
                        code=1000,
                        reason="Viewer disconnected",
                    )
                    await agent.ws.send_str(close_env.model_dump_json())
                except Exception:
                    pass

        return ws

    # ---------------- Setup Routes ----------------
    app.router.add_get("/stream/agent/register", handle_agent_register)
    app.router.add_get(
        "/gateway/v1/internal/profiles/{profile_id}/visibility",
        handle_supervisor_visibility,
    )
    app.router.add_post(
        "/gateway/v1/internal/profiles/{profile_id}/quota",
        handle_supervisor_quota,
    )
    app.router.add_post(
        "/gateway/v1/internal/profiles/{profile_id}/disconnect",
        handle_supervisor_disconnect,
    )
    app.router.add_get("/stream/{profile_id}/signal", handle_viewer_signal)

    # ---------------- Background Tasks ----------------
    async def background_loop(application: web.Application) -> Any:
        async def monitor_heartbeats() -> None:
            while True:
                try:
                    sleep_interval = min(
                        1.0, max(0.2, config.agent_heartbeat_timeout_sec / 4.0)
                    )
                    await asyncio.sleep(sleep_interval)
                    now = time.time()
                    timed_out = registry.check_heartbeat_timeouts(
                        now=now, timeout_sec=config.agent_heartbeat_timeout_sec
                    )
                    for agent in timed_out:
                        logger.warning(
                            "Agent for profile %s timed out (>30s). Evicting.",
                            agent.profile_id,
                        )
                        if not agent.ws.closed:
                            await agent.ws.close(
                                code=1001, message=b"Heartbeat timeout"
                            )
                        # Disconnect viewers bound to this timed-out agent session
                        await close_viewers_for_session(
                            agent.agent_session_id,
                            code=1001,
                            message=b"Stream Agent disconnected",
                        )

                    # Tick rotation coordinator
                    await rotation.tick(now=now)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(
                        "Error in Gateway background loop: %s", type(e).__name__
                    )

        task = asyncio.create_task(monitor_heartbeats())
        yield
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await api.close()

    app.cleanup_ctx.append(background_loop)
    return app
