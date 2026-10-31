"""Check exported wire schema against registration and tunnel traffic."""

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]


def test_exported_stream_schema_matches_models():
    spec = importlib.util.spec_from_file_location(
        "export_stream_protocol", ROOT / "scripts/export_stream_protocol.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (
        json.loads((ROOT / "schemas/stream/agent_protocol.json").read_text())
        == module.stream_protocol_schema()
    )


def test_stream_schema_accepts_protocol_packets_without_visibility_update():
    schema = json.loads((ROOT / "schemas/stream/agent_protocol.json").read_text())
    validator = Draft202012Validator(schema)
    identity = dict(
        version="v2", profile_id="profile_1", runtime_instance_id="runtime:1"
    )
    packets = [
        dict(
            identity, action="register", agent_session_id=None, conn_id=None, payload={}
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
