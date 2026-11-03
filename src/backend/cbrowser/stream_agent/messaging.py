"""Stateless Gateway protocol envelope and payload construction."""

from __future__ import annotations

import json
from typing import Any

from .policy_rules import iso_now
from .protocol import (
    AgentHeartbeatEnvelope,
    AgentHeartbeatPayload,
    AgentRegisterEnvelope,
    AgentRegisterPayload,
    GatewayTunnelEnvelope,
)

# iso_now is re-exported from policy_rules (single definition, t022 A48);
# consumers import it from here by name. No __all__ is declared: the
# module's public surface is its builder functions plus this re-export,
# and a partial __all__ would misstate it (review t022_code_f014).


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
        video_streaming_mode=config.video_streaming_mode,
        width=config.width,
        height=config.height,
    )


def build_register_envelope(
    config: Any, payload: AgentRegisterPayload, timestamp: str
) -> AgentRegisterEnvelope:
    return AgentRegisterEnvelope(
        profile_id=config.profile_id,
        runtime_instance_id=config.runtime_instance_id,
        payload=payload,
        timestamp=timestamp,
    )


def build_heartbeat_envelope(
    config: Any,
    session_id: str,
    payload: AgentHeartbeatPayload,
    timestamp: str,
) -> AgentHeartbeatEnvelope:
    return AgentHeartbeatEnvelope(
        profile_id=config.profile_id,
        runtime_instance_id=config.runtime_instance_id,
        agent_session_id=session_id,
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
