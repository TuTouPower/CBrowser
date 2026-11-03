"""Exported stop contracts must preserve the runtime and operation fences."""

import json
import runpy
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_export_matches_control_models_and_requires_stop_fences():
    export = runpy.run_path(str(ROOT / "scripts/export_supervisor_protocol.py"))
    schema = json.loads((ROOT / "schemas/runtime/supervisor_protocol.json").read_text())
    assert schema == export["supervisor_protocol_schema"]()
    validator = jsonschema.Draft202012Validator(schema["$defs"]["StopProfileRequest"])
    body = {"profile_id": "p1", "runtime_instance_id": "i1", "operation_id": "op1"}
    validator.validate(body)
    for required in ("runtime_instance_id", "operation_id"):
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(
                {key: value for key, value in body.items() if key != required}
            )


def test_supervisor_schema_uses_entry_index_convention():
    """A41: consumers enter via the messages index; no top-level anyOf."""
    schema = json.loads((ROOT / "schemas/runtime/supervisor_protocol.json").read_text())
    assert "anyOf" not in schema
    assert schema["version"] == "1.0.0"
    assert set(schema["messages"]) == {
        "StartProfileRequest",
        "StartProfileResponse",
        "StopProfileRequest",
        "StopProfileResponse",
        "ResetBlockedRequest",
        "ResetBlockedResponse",
        "ProfileRuntimeStatus",
        # t022/A55: search-defaults observation + retry join the protocol.
        "SearchDefaultsRetryRequest",
        "SearchDefaultsStatusResponse",
    }
    for name in schema["messages"]:
        assert schema["messages"][name] == {
            "$id": f"#/$defs/{name}",
            "$ref": f"#/$defs/{name}",
        }
    for definition in schema["$defs"].values():
        assert "$id" not in definition

    def entry(message: str) -> jsonschema.Draft202012Validator:
        return jsonschema.Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": f"#/$defs/{message}"}
        )

    entry("StartProfileRequest").validate({"profile_id": "p1"})
    entry("ProfileRuntimeStatus").validate({"profile_id": "p1"})
    with pytest.raises(jsonschema.ValidationError):
        entry("StartProfileRequest").validate({"profile_id": "p1", "bogus": 1})
    with pytest.raises(jsonschema.ValidationError):
        # A stop request is not a valid start request entry.
        entry("StartProfileRequest").validate(
            {"profile_id": "p1", "runtime_instance_id": "i1", "operation_id": "o1"}
        )

    # Every message in the index accepts a minimal valid packet through
    # its own entry point (full coverage, not a sample).
    valid_packets = {
        "StartProfileRequest": {"profile_id": "p1"},
        "StartProfileResponse": {
            "profile_id": "p1",
            "status": "starting",
            "runtime_instance_id": "i1",
            "udp_mux_port": 30001,
            "browser_container": "b",
            "stream_container": "s",
        },
        "StopProfileRequest": {
            "profile_id": "p1",
            "runtime_instance_id": "i1",
            "operation_id": "o1",
        },
        "StopProfileResponse": {"profile_id": "p1", "status": "stopped"},
        # t022/A55 messages.
        "SearchDefaultsRetryRequest": {
            "profile_id": "p1",
            "runtime_instance_id": "i1",
            "request_id": "r1",
        },
        "SearchDefaultsStatusResponse": {"profile_id": "p1"},
        "ResetBlockedRequest": {"profile_id": "p1"},
        "ResetBlockedResponse": {"profile_id": "p1"},
        "ProfileRuntimeStatus": {"profile_id": "p1"},
    }
    assert set(valid_packets) == set(schema["messages"])
    for message, packet in valid_packets.items():
        entry(message).validate(packet)
