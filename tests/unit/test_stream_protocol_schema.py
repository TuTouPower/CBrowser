"""Check exported wire schema against registration and tunnel traffic."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from scripts.export_stream_protocol import stream_protocol_schema

ROOT = Path(__file__).resolve().parents[2]


def test_exported_stream_schema_matches_models():
    assert (
        json.loads((ROOT / "schemas/stream/agent_protocol.json").read_text())
        == stream_protocol_schema()
    )


def test_stream_schema_accepts_protocol_packets_without_visibility_update():
    schema = json.loads((ROOT / "schemas/stream/agent_protocol.json").read_text())
    validator = Draft202012Validator(schema)
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
    packets = [
        dict(
            identity,
            action="register",
            agent_session_id=None,
            conn_id=None,
            payload=register_payload,
        ),
        dict(identity, status="ok", agent_session_id="session:1"),
        dict(
            identity,
            type="msg",
            agent_session_id="session:1",
            conn_id="viewer:1",
            data="HELLO",
        ),
        dict(
            identity,
            action="supervisor_quota",
            agent_session_id="session:1",
            payload={"max_fps_cap": 15.0},
        ),
        dict(
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
    ]
    for packet in packets:
        validator.validate(packet)
    visibility = dict(
        packets[3],
        action="visibility_update",
        payload={"viewer_id": "viewer:1", "visible": True},
    )
    for invalid in [
        dict(packets[0], version="v1"),
        dict(packets[2], unexpected=True),
        visibility,
    ]:
        with pytest.raises(ValidationError):
            validator.validate(invalid)
