"""Check exported wire schema against registration and tunnel traffic.

Packets are validated through the document's per-message entry points
(``messages`` index -> ``$defs``) rather than the removed top-level
``anyOf`` union entry (A41).
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from scripts.export_stream_protocol import stream_protocol_schema

ROOT = Path(__file__).resolve().parents[2]


def _load_schema() -> dict:
    return json.loads((ROOT / "schemas/stream/agent_protocol.json").read_text())


def _entry_validator(schema: dict, message: str) -> Draft202012Validator:
    assert schema["messages"][message] == {
        "$id": f"#/$defs/{message}",
        "$ref": f"#/$defs/{message}",
    }
    return Draft202012Validator(
        {"$defs": schema["$defs"], "$ref": f"#/$defs/{message}"}
    )


def test_exported_stream_schema_matches_models():
    assert _load_schema() == stream_protocol_schema()


def test_stream_schema_accepts_protocol_packets_without_visibility_update():
    schema = _load_schema()
    identity = {
        "version": "v2",
        "profile_id": "profile_1",
        "runtime_instance_id": "runtime:1",
    }
    register_payload = {
        "hostname": "stream-a",
        "profile_id": "profile_1",
        "runtime_instance_id": "runtime:1",
        "udp_port": 30006,
        "selkies_version": "2.1.0",
        "runtime_state": "ready",
        "config_version": 1,
    }
    packets = {
        "AgentRegisterEnvelope": dict(
            identity,
            action="register",
            agent_session_id=None,
            conn_id=None,
            payload=register_payload,
        ),
        "GatewayRegisterResponse": dict(
            identity, status="ok", agent_session_id="session:1"
        ),
        "GatewayTunnelEnvelope": dict(
            identity,
            type="msg",
            agent_session_id="session:1",
            conn_id="viewer:1",
            data="HELLO",
        ),
        "GatewayControlEnvelope": dict(
            identity,
            action="supervisor_quota",
            agent_session_id="session:1",
            payload={"max_fps_cap": 15.0},
        ),
        "AgentHeartbeatEnvelope": dict(
            identity,
            action="heartbeat",
            agent_session_id="session:1",
            payload={
                "runtime_state": "ready",
                "viewer_count": 1,
                "unpaused_video_consumers": 1,
                "capture_running": True,
            },
        ),
    }
    for message, packet in packets.items():
        _entry_validator(schema, message).validate(packet)

    visibility = dict(
        packets["GatewayControlEnvelope"],
        action="visibility_update",
        payload={"viewer_id": "viewer:1", "visible": True},
    )
    invalid = [
        ("AgentRegisterEnvelope", dict(packets["AgentRegisterEnvelope"], version="v1")),
        ("GatewayTunnelEnvelope", dict(packets["GatewayTunnelEnvelope"], unexpected=True)),
        ("GatewayControlEnvelope", visibility),
    ]
    for message, packet in invalid:
        with pytest.raises(ValidationError):
            _entry_validator(schema, message).validate(packet)
