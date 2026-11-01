"""Stateless Gateway protocol envelope and payload construction."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .protocol import (
    AgentAction,
    AgentHeartbeatPayload,
    AgentRegisterPayload,
    GatewayTunnelEnvelope,
    ProtocolEnvelope,
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_register_payload(
    config: Any, hostname: str, selkies_version: str
) -> AgentRegisterPayload:
    return AgentRegisterPayload(
        hostname=hostname,
        profile_id=config.profile_id,
        runtime_instance_id=config.runtime_instance_id,
        udp_port=config.udp_mux_port,
        selkies_version=selkies_version,
        runtime_state="ready",
        config_version=config.config_version,
        turn_host=config.turn_host,
        turn_port=config.turn_port,
        video_streaming_mode=config.video_streaming_mode,
        max_fps=int(config.max_fps),
        min_fps=int(config.min_fps),
        width=config.width,
        height=config.height,
    )


def build_register_envelope(
    config: Any, payload: AgentRegisterPayload, timestamp: str
) -> ProtocolEnvelope:
    return ProtocolEnvelope(
        action=AgentAction.REGISTER,
        profile_id=config.profile_id,
        runtime_instance_id=config.runtime_instance_id,
        payload=payload.model_dump(),
        timestamp=timestamp,
    )


def build_heartbeat_envelope(
    config: Any,
    session_id: str,
    payload: AgentHeartbeatPayload,
    timestamp: str,
) -> ProtocolEnvelope:
    return ProtocolEnvelope(
        action=AgentAction.HEARTBEAT,
        profile_id=config.profile_id,
        runtime_instance_id=config.runtime_instance_id,
        agent_session_id=session_id,
        payload=payload.model_dump(),
        timestamp=timestamp,
    )


def build_action_envelope(
    action: Any,
    *,
    profile_id: str,
    runtime_instance_id: str,
    session_id: str | None,
    conn_id: str | None,
    payload: dict[str, Any],
    timestamp: str,
) -> ProtocolEnvelope:
    return ProtocolEnvelope(
        action=action,
        profile_id=profile_id,
        runtime_instance_id=runtime_instance_id,
        agent_session_id=session_id,
        conn_id=conn_id,
        payload=payload,
        timestamp=timestamp,
    )


def tunnel_message_envelope(
    *,
    profile_id: str,
    runtime_instance_id: str,
    session_id: str | None,
    conn_id: str,
    data: str,
) -> GatewayTunnelEnvelope:
    return GatewayTunnelEnvelope(
        version="v2",
        type="msg",
        profile_id=profile_id,
        runtime_instance_id=runtime_instance_id,
        agent_session_id=session_id or "",
        conn_id=conn_id,
        data=data,
    )


def tunnel_close_envelope(
    *,
    profile_id: str,
    runtime_instance_id: str,
    session_id: str | None,
    conn_id: str,
    code: int,
    reason: str,
) -> GatewayTunnelEnvelope:
    return GatewayTunnelEnvelope(
        version="v2",
        type="close",
        profile_id=profile_id,
        runtime_instance_id=runtime_instance_id,
        agent_session_id=session_id,
        conn_id=conn_id,
        code=code,
        reason=reason,
    )


def normalize_close_code(close_code: Any) -> int:
    if type(close_code) is not int or not 1000 <= close_code <= 4999:
        return 1000
    return close_code


def parse_hello_metadata(
    data: str,
) -> tuple[list[str], dict[str, Any]] | None:
    parts = data.split(" ", 2)
    if len(parts) <= 2:
        return None
    return parts, json.loads(parts[2])


def inject_controller_token(
    parts: list[str], meta: dict[str, Any], token: str
) -> str:
    meta["client_token"] = token
    return f"{parts[0]} {parts[1]} {json.dumps(meta)}"
