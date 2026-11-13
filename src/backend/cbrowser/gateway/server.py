"""Stream Gateway application, route handlers, and background tasks."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from aiohttp import WSMsgType, web
from cbrowser.secret_files import read_secret_file
from cbrowser.stream_agent.protocol import (
    MAX_STREAM_FRAME_SIZE,
    MAX_TUNNEL_DATA_SIZE,
    MAX_TUNNEL_ENVELOPE_SIZE,
    AgentAction,
    AgentRegisterEnvelope,
    GatewayControlEnvelope,
    GatewayRegisterResponse,
    RegistrationRejection,
    GatewayTunnelEnvelope,
    SupervisorQuotaPayload,
    serialize_tunnel_envelope,
    validate_agent_envelope,
)
from cbrowser.shared.agent_credentials import AgentCredentials
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .api_client import GatewayApiClient
from cbrowser.shared.client_ip import parse_trusted_proxy_cidrs, resolve_client_ip
from .config import GatewayConfig
from cbrowser.shared.endpoints import normalize_origin
from .registry import (
    AgentRegistry,
    AuthorizationThrottle,
    RegisteredAgent,
    RegistrationThrottle,
)

logger = logging.getLogger("cbrowser.gateway.server")


def _error_response(
    status: int, error: str, message: str, *, retryable: bool = False
) -> web.Response:
    """Unified ErrorResponse body (t056 A15): the same ``error`` /
    ``message`` / ``retryable`` shape the API returns, so a Gateway
    failure is diagnosable with the same tooling.  WebSocket handshake
    failures below still answer plain text: a WS upgrade cannot carry
    a JSON error body."""
    return web.json_response(
        {"error": error, "message": message, "retryable": retryable},
        status=status,
    )


class _QuotaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_instance_id: str
    max_fps_cap: float | None = None
    reason: str | None = None


class _DisconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_instance_id: str


@dataclass
class ViewerEntry:
    conn_id: str
    profile_id: str
    agent_session_id: str
    ws: web.WebSocketResponse


async def deliver_supervisor_quota(agent: RegisteredAgent, payload: Any) -> bool:
    """Send a quota envelope to the Agent; False when delivery fails.

    Extracted so the failure mapping (explicit 503, never a bare 500) is
    unit-testable without a live socket (t022 A16).
    """
    env = GatewayControlEnvelope(
        version="v2",
        action=AgentAction.SUPERVISOR_QUOTA,
        profile_id=agent.profile_id,
        runtime_instance_id=agent.instance_id,
        agent_session_id=agent.agent_session_id,
        payload=payload,
    )
    try:
        await agent.ws.send_str(env.model_dump_json())
    except Exception as exc:  # noqa: BLE001 - any send failure is a delivery failure
        logger.warning(
            "Failed delivering quota to Agent for profile %s: %s",
            agent.profile_id,
            type(exc).__name__,
        )
        return False
    return True


def supervisor_fence_failure(
    agent: RegisteredAgent | None,
    profile_id: str,
    runtime_instance_id: str,
) -> web.Response | None:
    """Availability + instance fence shared by the supervisor routes.

    Returns the failure response to send, or None when the caller may
    proceed. Pure decision logic (t022 A48): handlers keep only the I/O.
    """
    if agent is None or agent.ws.closed:
        return _error_response(
            503,
            "agent_unavailable",
            f"Agent for profile {profile_id} is unavailable",
            retryable=True,
        )
    if agent.instance_id != runtime_instance_id:
        return _error_response(
            409,
            "instance_conflict",
            f"Instance fence conflict: active instance is "
            f"{agent.instance_id}, requested {runtime_instance_id}",
        )
    return None


async def close_profile_viewers_and_notify(
    viewers: dict[str, ViewerEntry],
    profile_id: str,
    agent: RegisteredAgent,
) -> bool:
    """Close every viewer of a profile and notify the Agent, per target.

    Each viewer's close and each Agent notification is isolated: a failure
    for one target never skips the remaining ones. Returns True when any
    Agent notification failed (the caller reports an explicit 503).
    """
    send_failed = False
    target_cids = [
        cid for cid, entry in list(viewers.items()) if entry.profile_id == profile_id
    ]
    for cid in target_cids:
        v_entry = viewers.pop(cid, None)
        if v_entry and not v_entry.ws.closed:
            try:
                await v_entry.ws.close(
                    code=1000, message=b"Supervisor disconnected viewers"
                )
            except Exception as exc:  # noqa: BLE001 - one viewer's failure must not skip the rest
                logger.debug(
                    "Failed closing viewer %s during disconnect: %s",
                    cid,
                    type(exc).__name__,
                )
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
            try:
                await agent.ws.send_str(close_env.model_dump_json())
            except Exception as exc:  # noqa: BLE001 - record and continue with remaining targets
                send_failed = True
                logger.warning(
                    "Failed notifying Agent of viewer disconnect: %s",
                    type(exc).__name__,
                )
    return send_failed


def create_gateway_app(
    config: GatewayConfig,
    api_client: GatewayApiClient | None = None,
) -> web.Application:
    """Builds and configures the aiohttp Gateway web application."""
    app = web.Application()
    trusted_proxy_cidrs = parse_trusted_proxy_cidrs(
        os.environ.get("CBROWSER_TRUSTED_PROXY_CIDRS")
    )

    def _resolve_source(request: web.Request) -> str:
        return resolve_client_ip(
            request.remote,
            request.headers.get("X-Forwarded-For"),
            trusted_proxy_cidrs,
        )

    credentials = AgentCredentials(config.agent_key_file)
    try:
        control_token = read_secret_file(
            config.gateway_token_file,
            label="Gateway control token",
            minimum_bytes=32,
        ).encode("utf-8")
    except RuntimeError as exc:
        raise ValueError(str(exc)) from None
    api = api_client or GatewayApiClient(config.api_url, config.api_token_file)

    registry = AgentRegistry()
    viewers: dict[str, ViewerEntry] = {}
    # Most recent registration refusal per profile (t026 AC-008): the
    # Supervisor diagnoses persistent unregistration through the control
    # plane instead of guessing why an Agent never appears.
    registration_rejections: dict[str, dict[str, Any]] = {}

    def _record_rejection(
        profile_id: str,
        runtime_instance_id: str,
        code: str,
        message: str,
        agent_build_id: str | None = None,
    ) -> RegistrationRejection:
        rejection = RegistrationRejection(
            code=code,
            message=message,
            gateway_build_id=config.build_id,
            agent_build_id=agent_build_id,
        )
        registration_rejections[profile_id] = {
            "runtime_instance_id": runtime_instance_id,
            "rejection": rejection.model_dump(),
            "at": time.time(),
        }
        return rejection

    async def _send_rejection(
        ws: web.WebSocketResponse,
        profile_id: str,
        runtime_instance_id: str,
        rejection: RegistrationRejection,
    ) -> None:
        response = GatewayRegisterResponse(
            version="v2",
            status="error",
            profile_id=profile_id,
            runtime_instance_id=runtime_instance_id,
            error=rejection.code,
            gateway_build_id=config.build_id,
            rejection=rejection,
        )
        try:
            await ws.send_str(response.model_dump_json())
        except Exception as exc:  # noqa: BLE001 - dead socket is reaped by the caller
            logger.debug(
                "Failed sending registration rejection: %s", type(exc).__name__
            )

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
            if v_entry and not v_entry.ws.closed:
                try:
                    await v_entry.ws.close(code=code, message=message)
                except Exception as exc:  # noqa: BLE001 - best-effort viewer socket cleanup on agent disconnect
                    logger.debug(
                        "Failed closing viewer ws %s: %s", cid, type(exc).__name__
                    )

    registration_throttle = RegistrationThrottle()
    authorization_throttle = AuthorizationThrottle()

    # ---------------- Supervisor Auth Helper ----------------
    def _check_supervisor_auth(request: web.Request) -> web.Response | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return _error_response(
                401,
                "unauthorized",
                "Missing or invalid Bearer authorization header",
            )
        provided = auth[len("Bearer ") :].strip().encode("utf-8")
        if not hmac.compare_digest(provided, control_token):
            return _error_response(401, "unauthorized", "Unauthorized control token")
        return None

    # ---------------- Health Route (t027) ----------------
    async def handle_health(request: web.Request) -> web.Response:
        # Unauthenticated liveness for the compose healthcheck: the probe
        # runs inside the deployment network and learns nothing beyond the
        # process being up, mirroring the API /api/v1/health contract.
        return web.json_response({"status": "ok", "role": "gateway"})

    # ---------------- Supervisor Control Routes ----------------
    async def handle_supervisor_visibility(request: web.Request) -> web.Response:
        auth_err = _check_supervisor_auth(request)
        if auth_err:
            return auth_err

        profile_id = request.match_info["profile_id"]
        runtime_instance_id = request.query.get("runtime_instance_id")
        if not runtime_instance_id:
            return _error_response(
                400,
                "bad_request",
                "runtime_instance_id query parameter is required",
            )

        agent = registry.get(profile_id)
        fence_failure = supervisor_fence_failure(
            agent, profile_id, runtime_instance_id
        )
        if fence_failure is not None:
            return fence_failure

        # Only the Agent's last health report (Selkies peer state) is returned.
        if agent.unpaused_video_consumers is None or agent.capture_running is None:
            return _error_response(
                503,
                "agent_unavailable",
                f"Agent for profile {profile_id} has not reported yet",
                retryable=True,
            )
        return web.json_response(
            {
                "has_foreground_viewers": agent.unpaused_video_consumers > 0,
                "unpaused_video_consumers": agent.unpaused_video_consumers,
                "capture_running": agent.capture_running,
            }
        )

    async def handle_supervisor_registration(request: web.Request) -> web.Response:
        """Registration state + last structured refusal for one profile."""
        auth_err = _check_supervisor_auth(request)
        if auth_err:
            return auth_err
        profile_id = request.match_info["profile_id"]
        agent = registry.get(profile_id)
        recorded = registration_rejections.get(profile_id)
        body: dict[str, Any] = {
            "profile_id": profile_id,
            "gateway_build_id": config.build_id,
            "registered": bool(agent is not None and not agent.ws.closed),
            "runtime_instance_id": agent.instance_id if agent else None,
            "agent_build_id": agent.build_id if agent else None,
            "selkies_version": agent.selkies_version if agent else None,
            "rejection": recorded["rejection"] if recorded else None,
            "rejection_runtime_instance_id": (
                recorded["runtime_instance_id"] if recorded else None
            ),
        }
        return web.json_response(body)

    async def handle_supervisor_quota(request: web.Request) -> web.Response:
        auth_err = _check_supervisor_auth(request)
        if auth_err:
            return auth_err

        profile_id = request.match_info["profile_id"]
        try:
            body = await request.json()
        except (ValueError, json.JSONDecodeError):
            return _error_response(400, "bad_request", "Invalid JSON body")
        if not isinstance(body, dict):
            return _error_response(400, "bad_request", "Invalid JSON body")

        try:
            quota_request = _QuotaRequest.model_validate(body)
            payload = SupervisorQuotaPayload.model_validate(
                {
                    "max_fps_cap": quota_request.max_fps_cap,
                    "reason": quota_request.reason,
                }
            )
        except ValidationError:
            return _error_response(400, "bad_request", "Invalid supervisor quota")
        runtime_instance_id = quota_request.runtime_instance_id

        agent = registry.get(profile_id)
        fence_failure = supervisor_fence_failure(
            agent, profile_id, runtime_instance_id
        )
        if fence_failure is not None:
            return fence_failure

        if not await deliver_supervisor_quota(agent, payload):
            return _error_response(
                503, "service_unavailable", "Failed to deliver quota to Agent", retryable=True
            )
        return web.json_response({"status": "ok"})

    async def handle_supervisor_disconnect(request: web.Request) -> web.Response:
        auth_err = _check_supervisor_auth(request)
        if auth_err:
            return auth_err

        profile_id = request.match_info["profile_id"]
        try:
            body = await request.json()
        except (ValueError, json.JSONDecodeError):
            return _error_response(400, "bad_request", "Invalid JSON body")
        if not isinstance(body, dict):
            return _error_response(400, "bad_request", "Invalid JSON body")

        try:
            disconnect_request = _DisconnectRequest.model_validate(body)
        except ValidationError:
            return _error_response(400, "bad_request", "Invalid disconnect request")
        runtime_instance_id = disconnect_request.runtime_instance_id

        agent = registry.get(profile_id)
        fence_failure = supervisor_fence_failure(
            agent, profile_id, runtime_instance_id
        )
        if fence_failure is not None:
            return fence_failure

        # Disconnect viewer WebSockets only; do NOT disconnect Agent WS.
        send_failed = await close_profile_viewers_and_notify(
            viewers, profile_id, agent
        )
        if send_failed:
            return _error_response(
                503,
                "service_unavailable",
                "Failed to notify Agent of viewer disconnect",
                retryable=True,
            )
        return web.json_response({"status": "ok"})

    # ---------------- Agent Register Route ----------------
    async def handle_agent_register(request: web.Request) -> web.WebSocketResponse:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return web.Response(status=401, text="Unauthorized Agent")
        raw_token = auth.removeprefix("Bearer ").strip()
        source = _resolve_source(request)
        if not registration_throttle.reserve(source):
            logger.warning("Agent registration rate limited for source")
            return web.Response(status=429, text="Too many registration attempts")
        handshake_complete = False
        credential_failure = False
        try:

            profile_id = request.query.get("profile_id", "")
            instance_id = request.query.get("runtime_instance_id", "")
            if (
                not profile_id
                or not instance_id
                or not re.fullmatch(r"[a-zA-Z0-9_-]+", profile_id)
                or not re.fullmatch(r"[a-zA-Z0-9_\-\.:]{1,128}", instance_id)
            ):
                return web.Response(status=400, text="Missing registration identity")
            if not credentials.verify(raw_token, profile_id, instance_id):
                credential_failure = True
                if profile_id and instance_id:
                    _record_rejection(
                        profile_id,
                        instance_id,
                        "unauthorized",
                        "Agent credentials rejected",
                    )
                return web.Response(status=401, text="Invalid Agent credentials")
            runtime_info = await api.get_profile_runtime(profile_id)
            if not runtime_info or runtime_info.get("runtime_instance_id") != instance_id:
                _record_rejection(
                    profile_id,
                    instance_id,
                    "instance_not_bound",
                    "Instance not currently bound to profile",
                )
                return web.Response(
                    status=403, text="Instance not currently bound to profile"
                )

            ws = web.WebSocketResponse(max_msg_size=MAX_STREAM_FRAME_SIZE)
            await ws.prepare(request)

            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=10.0)
            except (TimeoutError, ConnectionError):
                logger.warning("Agent registration timed out before first packet")
                await ws.close(code=1008, message=b"Registration timeout")
                return ws
            if msg.type != WSMsgType.TEXT:
                await ws.close(code=1003, message=b"Expected text registration packet")
                return ws

            try:
                reg_raw = json.loads(msg.data)
                envelope = AgentRegisterEnvelope.model_validate(reg_raw)
            except Exception as e:  # noqa: BLE001 - registration packet decoding boundary: any malformed packet closes the handshake, mirroring the other decode boundaries in this module
                logger.warning("Agent registration payload invalid: %s", type(e).__name__)
                offered_version = (
                    reg_raw.get("version") if isinstance(reg_raw, dict) else None
                )
                offered_build = None
                if isinstance(reg_raw, dict) and isinstance(
                    reg_raw.get("payload"), dict
                ):
                    offered_build = reg_raw["payload"].get("build_id")
                code = (
                    "unsupported_version"
                    if offered_version not in (None, "v2")
                    else "invalid_payload"
                )
                rejection = _record_rejection(
                    profile_id,
                    instance_id,
                    code,
                    "Registration payload rejected",
                    agent_build_id=offered_build
                    if isinstance(offered_build, str)
                    else None,
                )
                await _send_rejection(ws, profile_id, instance_id, rejection)
                await ws.close(code=1008, message=b"Invalid registration payload")
                return ws

            payload = envelope.payload
            pid = payload.profile_id
            iid = payload.runtime_instance_id
            if pid != profile_id or iid != instance_id:
                logger.warning(
                    "Agent registration identity mismatch: query=%s/%s payload=%s/%s",
                    profile_id,
                    instance_id,
                    pid,
                    iid,
                )
                rejection = _record_rejection(
                    profile_id,
                    instance_id,
                    "identity_mismatch",
                    "Registration identity mismatch",
                    agent_build_id=payload.build_id,
                )
                await _send_rejection(ws, profile_id, instance_id, rejection)
                await ws.close(
                    code=1008, message=b"Registration identity mismatch"
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
                ws=ws,
                last_heartbeat=registry.now(),
                build_id=payload.build_id,
            )
            registration_rejections.pop(pid, None)

            old_agent = registry.register(agent)
            if old_agent:
                # Post-registration cleanup is isolated: a failure here
                # must not escape and strand the fresh registration
                # without a message pump (review t022_code_f004).
                try:
                    await close_viewers_for_session(
                        old_agent.agent_session_id,
                        code=1001,
                        message=b"Stream Agent session replaced",
                    )
                except Exception as exc:  # noqa: BLE001 - superseded session cleanup is best-effort
                    logger.debug(
                        "Failed closing viewers of superseded session: %s",
                        type(exc).__name__,
                    )
                if not old_agent.ws.closed:
                    try:
                        await old_agent.ws.close(
                            code=1000, message=b"Superceded by new registration"
                        )
                    except Exception as exc:  # noqa: BLE001 - best-effort closing of superseded agent connection
                        logger.debug(
                            "Failed closing superseded agent ws: %s",
                            type(exc).__name__,
                        )

            # The registration is complete once the registry accepts it:
            # release the reservation as a success BEFORE sending the ACK,
            # so a broken ACK send (dead socket) cannot misrecord a valid
            # registration as a throttle failure (review t022_code_f007).
            registration_throttle.release(source, success=True)
            handshake_complete = True

            # Send ACK (best-effort): if the socket is already dead the
            # pump below observes the close immediately and reaps the
            # registration; an exception here must not strand it.
            ack = GatewayRegisterResponse(
                version="v2",
                status="ok",
                profile_id=pid,
                runtime_instance_id=iid,
                agent_session_id=session_id,
                gateway_build_id=config.build_id,
            )
            try:
                await ws.send_str(ack.model_dump_json())
            except Exception as exc:  # noqa: BLE001 - dead socket is reaped by the pump
                logger.debug(
                    "Failed sending registration ACK: %s", type(exc).__name__
                )
        finally:
            if not handshake_complete:
                # Only rejected credentials consume the failure budget.
                # Timeouts, cancellations, and post-auth protocol errors
                # release the in-flight reservation without letting a
                # flaky Agent or a shared source address exhaust the
                # brute-force budget it never spent.
                registration_throttle.release(
                    source, success=not credential_failure
                )

        # Pump messages from Agent
        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    try:
                        if len(m.data.encode("utf-8")) > MAX_TUNNEL_ENVELOPE_SIZE:
                            # Same envelope budget the Agent applies in the
                            # opposite direction (t022 A15): an oversized
                            # frame closes this connection with 1009; other
                            # connections are unaffected.
                            logger.warning(
                                "Closing Agent connection: envelope over budget"
                            )
                            await ws.close(
                                code=1009, message=b"Message too large"
                            )
                            break
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
                        else:
                            agent_env = validate_agent_envelope(pkt)
                            if (
                                agent_env.profile_id != pid
                                or agent_env.runtime_instance_id != iid
                                or agent_env.agent_session_id != session_id
                            ):
                                logger.warning(
                                    "Dropped agent action packet: identity mismatch "
                                    "(action=%s)",
                                    agent_env.action,
                                )
                                continue

                            if agent_env.action == AgentAction.HEARTBEAT:
                                beat = agent_env.payload
                                registry.update_heartbeat(
                                    pid,
                                    iid,
                                    session_id,
                                    runtime_state=beat.runtime_state,
                                )
                                agent.unpaused_video_consumers = (
                                    beat.unpaused_video_consumers
                                )
                                agent.capture_running = beat.capture_running
                            elif (
                                agent_env.action
                                == AgentAction.HUMAN_INPUT_TAKEOVER
                            ):
                                # t031: foreground human input preempts
                                # agent control. Forward to the API, which
                                # owns the transition and the tunnel close.
                                # A failed report is logged, never fatal
                                # to the Gateway pump; the takeover is
                                # idempotent, so the human's next
                                # classified input re-reports it.
                                takeover = agent_env.payload
                                reported = await api.report_human_takeover(
                                    pid,
                                    takeover.viewer_conn_id,
                                    takeover.input_kind,
                                )
                                if reported is None:
                                    logger.warning(
                                        "Human takeover report failed: "
                                        "profile=%s conn=%s kind=%s",
                                        pid,
                                        takeover.viewer_conn_id,
                                        takeover.input_kind,
                                    )
                    except Exception as e:  # noqa: BLE001 - agent message handling loop isolation prevents gateway drop
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
        source = _resolve_source(request)

        if not authorization_throttle.allow(source, profile_id):
            return web.Response(
                status=429, text="Too many viewer authorization failures"
            )

        # 1. Origin verification (normalized scheme/host/port) against the
        # deploy-derived whitelist (t054): the port is fixed at deploy time,
        # so there is no publication state to re-read here.
        raw_origin = request.headers.get("Origin", "")
        try:
            origin = normalize_origin(raw_origin)
        except ValueError:
            authorization_throttle.record_failure(source, profile_id)
            return web.Response(status=403, text="Origin not allowed")
        if origin not in config.allowed_origins:
            authorization_throttle.record_failure(source, profile_id)
            return web.Response(status=403, text="Origin not allowed")

        # 2. Session cookie verification
        session_cookie = request.cookies.get("cbrowser_session")
        if not session_cookie:
            authorization_throttle.record_failure(source, profile_id)
            return web.Response(
                status=401,
                text="Authentication required: cbrowser_session cookie missing",
            )

        allowed, reason = await api.authorize_viewer(session_cookie, origin, profile_id)
        if not allowed:
            authorization_throttle.record_failure(source, profile_id)
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

        ws = web.WebSocketResponse(max_msg_size=MAX_STREAM_FRAME_SIZE)
        await ws.prepare(request)

        conn_id = str(uuid.uuid4())
        viewers[conn_id] = ViewerEntry(
            conn_id=conn_id,
            profile_id=profile_id,
            agent_session_id=agent.agent_session_id,
            ws=ws,
        )

        try:
            # 4. Open tunnel to Agent
            open_env = GatewayTunnelEnvelope(
                version="v2",
                type="open",
                profile_id=profile_id,
                runtime_instance_id=agent.instance_id,
                agent_session_id=agent.agent_session_id,
                conn_id=conn_id,
            )
            await agent.ws.send_str(open_env.model_dump_json())
        except Exception as exc:  # noqa: BLE001 - viewer connection handshake error triggers clean teardown
            logger.warning(
                "Viewer initialization failed: error_type=%s", type(exc).__name__
            )
            viewers.pop(conn_id, None)
            if not ws.closed:
                try:
                    await ws.close(code=1011, message=b"Viewer initialization failed")
                except Exception as exc_close:  # noqa: BLE001 - best-effort viewer socket close
                    logger.debug(
                        "Failed closing viewer ws: %s", type(exc_close).__name__
                    )
            if not agent.ws.closed:
                try:
                    await agent.ws.send_str(
                        GatewayTunnelEnvelope(
                            version="v2",
                            type="close",
                            profile_id=profile_id,
                            runtime_instance_id=agent.instance_id,
                            agent_session_id=agent.agent_session_id,
                            conn_id=conn_id,
                            code=1011,
                            reason="Viewer initialization failed",
                        ).model_dump_json()
                    )
                except Exception as exc_notify:  # noqa: BLE001 - best-effort agent notification on handshake failure
                    logger.debug(
                        "Failed notifying agent of viewer failure: %s",
                        type(exc_notify).__name__,
                    )
            return ws

        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    text = m.data
                    if '"cbrowser"' in text:
                        try:
                            parsed = json.loads(text)
                        except ValueError:
                            parsed = None
                        if isinstance(parsed, dict) and "cbrowser" in parsed:
                            continue
                    if not agent.ws.closed:
                        # Forward to Agent as tunnel msg. Oversized viewer
                        # data is a controlled 1009 close of this viewer
                        # connection only (A15); the Gateway keeps serving
                        # every other connection.
                        try:
                            if len(text.encode("utf-8")) > MAX_TUNNEL_DATA_SIZE:
                                raise ValueError("Viewer data exceeds budget")
                            msg_env = GatewayTunnelEnvelope(
                                version="v2",
                                type="msg",
                                profile_id=profile_id,
                                runtime_instance_id=agent.instance_id,
                                agent_session_id=agent.agent_session_id,
                                conn_id=conn_id,
                                data=text,
                            )
                            payload = serialize_tunnel_envelope(msg_env)
                        except (ValidationError, ValueError):
                            logger.warning(
                                "Viewer message exceeded the shared tunnel "
                                "budget; closing with 1009"
                            )
                            await ws.close(
                                code=1009, message=b"Message too large"
                            )
                            break
                        await agent.ws.send_str(payload)
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
                except Exception as exc_close:  # noqa: BLE001 - best-effort close notification to agent on viewer exit
                    logger.debug(
                        "Failed notifying agent of viewer disconnect: %s",
                        type(exc_close).__name__,
                    )

        return ws

    # ---------------- Setup Routes ----------------
    app.router.add_get("/gateway/v1/health", handle_health)
    app.router.add_get("/stream/agent/register", handle_agent_register)
    app.router.add_get(
        "/gateway/v1/internal/profiles/{profile_id}/visibility",
        handle_supervisor_visibility,
    )
    app.router.add_get(
        "/gateway/v1/internal/profiles/{profile_id}/registration",
        handle_supervisor_registration,
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
                    timed_out = registry.check_heartbeat_timeouts(
                        now=registry.now(),
                        timeout_sec=config.agent_heartbeat_timeout_sec,
                    )
                    for agent in timed_out:
                        logger.warning(
                            "Agent for profile %s timed out (>%.0fs). Evicting.",
                            agent.profile_id,
                            config.agent_heartbeat_timeout_sec,
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
                except asyncio.CancelledError:
                    break
                except Exception as e:  # noqa: BLE001 - background monitor loop isolation prevents gateway exit
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
