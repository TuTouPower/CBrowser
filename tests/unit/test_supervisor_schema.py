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
