"""A16 read-only protocol drift guards.

The ``messages``-index assertions that previously lived in
``test_supervisor_schema.py`` and ``test_stream_protocol_schema.py`` hardcoded
the same 14/5-name list as the export scripts, so both shared the exact
omission (the protocols actually define 22/6 wire messages) and could never
detect a missing model. Those hardcoded-index tests were deleted. The oracle
here is the production protocol module itself (class introspection plus an
explicit payload/base classification) and the real RPC / envelope consumption
entry points, never a copy of the export's list. Every artifact check writes
only to a temporary directory and compares bytes against the checked-in file.
"""

import json
import secrets
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import jsonschema
import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

import cbrowser.stream_agent.protocol as stream_proto
import cbrowser.supervisor.protocol as supervisor_proto
from scripts.export_openapi import export_openapi_schema
from scripts.export_runtime_agent_protocol import agent_protocol_schema
from scripts.export_stream_protocol import stream_protocol_schema
from scripts.export_supervisor_protocol import supervisor_protocol_schema

ROOT = Path(__file__).resolve().parents[2]

STREAM_NON_WIRE = frozenset(
    {
        "SupervisorQuotaPayload",
        "RegistrationRejection",
        "_AgentEnvelope",
        "AgentRegisterPayload",
        "AgentHeartbeatPayload",
        "HumanInputTakeoverPayload",
    }
)

SUPERVISOR_OMISSIONS = frozenset(
    {
        "PreviewPolicySyncResponse",
        "CloseTunnelsRequest",
        "CloseTunnelsResponse",
        "AttendantDialogsResponse",
        "AnswerAttendantDialogRequest",
        "AnswerAttendantDialogResponse",
        "RebuildEdgeRequest",
        "ConvergeStreamsRequest",
    }
)

STREAM_OMISSIONS = frozenset({"AgentHumanInputTakeoverEnvelope"})

PROTOCOL_ARTIFACTS = (
    "schemas/runtime/supervisor_protocol.json",
    "schemas/runtime/agent_protocol.json",
    "schemas/stream/agent_protocol.json",
    "schemas/openapi/cbrowser_v1.json",
    "schemas/openapi/cbrowser_internal.json",
)

TYPESCRIPT_ARTIFACT = "src/frontend/src/shared/api/generated/cbrowser_v1.d.ts"


class ProtocolDriftError(RuntimeError):
    pass


def _defined_model_names(module) -> set[str]:
    return {
        name
        for name, obj in vars(module).items()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == module.__name__
    }


def _registry_names(module, attr: str) -> tuple[str, ...]:
    registry = getattr(module, attr, None)
    if registry is None:
        return ()
    return tuple(member.__name__ for member in get_args(registry))


def assert_wire_registry_complete(module, registered_names, non_wire) -> set[str]:
    defined = _defined_model_names(module)
    expected_wire = defined - set(non_wire)
    registered = set(registered_names)
    if expected_wire != registered:
        raise ProtocolDriftError(
            f"unregistered wire models: {sorted(expected_wire - registered)}; "
            f"unexpected registrations: {sorted(registered - expected_wire)}"
        )
    return expected_wire


def assert_generated_matches_committed(relative, generated_bytes, tmp_path) -> None:
    scratch = tmp_path / ("generated_" + Path(relative).name)
    scratch.write_bytes(generated_bytes)
    committed = (ROOT / relative).read_bytes()
    if committed != scratch.read_bytes():
        raise ProtocolDriftError(f"checked-in artifact is stale: {relative}")


def _load(relative) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _entry_validator(schema, message):
    return jsonschema.Draft202012Validator(
        {"$defs": schema["$defs"], "$ref": f"#/$defs/{message}"}
    )


def test_supervisor_schema_covers_every_defined_wire_model():
    schema = _load("schemas/runtime/supervisor_protocol.json")
    assert set(schema["messages"]) == _defined_model_names(supervisor_proto)


def test_stream_schema_covers_every_defined_wire_model():
    schema = _load("schemas/stream/agent_protocol.json")
    expected = _defined_model_names(stream_proto) - STREAM_NON_WIRE
    assert set(schema["messages"]) == expected


def test_existing_omissions_are_present():
    supervisor = _load("schemas/runtime/supervisor_protocol.json")["messages"]
    stream = _load("schemas/stream/agent_protocol.json")["messages"]
    assert SUPERVISOR_OMISSIONS <= set(supervisor)
    assert STREAM_OMISSIONS <= set(stream)


def test_registries_are_the_single_explicit_source():
    supervisor_names = _registry_names(supervisor_proto, "SupervisorMessage")
    stream_names = _registry_names(stream_proto, "GatewayWireMessage")
    assert supervisor_names, "supervisor protocol has no explicit wire registry"
    assert stream_names, "stream protocol has no explicit wire registry"
    assert set(supervisor_names) == _defined_model_names(supervisor_proto)
    assert set(stream_names) == _defined_model_names(stream_proto) - STREAM_NON_WIRE
    assert set(supervisor_names) == set(
        _load("schemas/runtime/supervisor_protocol.json")["messages"]
    )
    assert set(stream_names) == set(
        _load("schemas/stream/agent_protocol.json")["messages"]
    )


def test_export_schemas_follow_the_registries():
    assert set(supervisor_protocol_schema()["messages"]) == set(
        _registry_names(supervisor_proto, "SupervisorMessage")
    )
    assert set(stream_protocol_schema()["messages"]) == set(
        _registry_names(stream_proto, "GatewayWireMessage")
    )


def test_payload_and_base_classes_are_not_entries():
    stream = _load("schemas/stream/agent_protocol.json")
    assert STREAM_NON_WIRE.isdisjoint(stream["messages"])
    for name in (
        "SupervisorQuotaPayload",
        "RegistrationRejection",
        "AgentRegisterPayload",
        "AgentHeartbeatPayload",
        "HumanInputTakeoverPayload",
    ):
        assert name in stream["$defs"]
    assert "_AgentEnvelope" not in stream["$defs"]
    supervisor = _load("schemas/runtime/supervisor_protocol.json")
    assert "SearchDefaultsStatus" in set(supervisor["$defs"]) - set(
        supervisor["messages"]
    )


def test_real_rpc_entry_points_are_covered(tmp_path):
    from cbrowser.supervisor.control_server import create_control_app

    token = tmp_path / "supervisor_token"
    token.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    token.chmod(0o600)
    app = create_control_app(SimpleNamespace(), token)
    consumed = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        response_model = route.response_model
        if (
            isinstance(response_model, type)
            and response_model.__module__ == supervisor_proto.__name__
        ):
            consumed.add(response_model.__name__)
        for param in route.dependant.body_params:
            annotation = getattr(param.field_info, "annotation", None)
            if (
                isinstance(annotation, type)
                and annotation.__module__ == supervisor_proto.__name__
            ):
                consumed.add(annotation.__name__)
    assert consumed
    assert consumed <= set(
        _load("schemas/runtime/supervisor_protocol.json")["messages"]
    )


def test_real_envelope_entry_points_are_covered():
    import typing

    from cbrowser.stream_agent.protocol import (
        AgentEnvelope,
        serialize_tunnel_envelope,
        validate_agent_envelope,
    )

    agent_names = {
        member.__name__ for member in get_args(get_args(AgentEnvelope)[0])
    }
    tunnel = typing.get_type_hints(serialize_tunnel_envelope)["envelope"]
    messages = set(_load("schemas/stream/agent_protocol.json")["messages"])
    assert agent_names <= messages
    assert tunnel.__name__ in messages
    takeover = {
        "version": "v2",
        "profile_id": "p1",
        "runtime_instance_id": "i1",
        "action": "human_input_takeover",
        "payload": {"input_kind": "key"},
    }
    assert isinstance(
        validate_agent_envelope(takeover),
        stream_proto.AgentHumanInputTakeoverEnvelope,
    )


def test_entry_index_convention():
    for relative, version in (
        ("schemas/runtime/supervisor_protocol.json", "1.0.0"),
        ("schemas/stream/agent_protocol.json", "v2"),
    ):
        schema = _load(relative)
        assert "anyOf" not in schema
        assert schema["version"] == version
        for name, entry in schema["messages"].items():
            assert entry == {"$id": f"#/$defs/{name}", "$ref": f"#/$defs/{name}"}
            assert name in schema["$defs"]
        for definition in schema["$defs"].values():
            assert "$id" not in definition


def test_omitted_message_packets_validate():
    supervisor = _load("schemas/runtime/supervisor_protocol.json")
    packets = {
        "PreviewPolicySyncResponse": {},
        "CloseTunnelsRequest": {"generation": 1},
        "CloseTunnelsResponse": {"profile_id": "p1", "generation": 1},
        "AttendantDialogsResponse": {"profile_id": "p1"},
        "AnswerAttendantDialogRequest": {"target_id": "t1"},
        "AnswerAttendantDialogResponse": {
            "profile_id": "p1",
            "dialog": {},
            "action": "accept",
        },
        "RebuildEdgeRequest": {
            "target_version": 1,
            "bind_host": "127.0.0.1",
            "https_port": 443,
            "caddyfile_path": "/x",
        },
        "ConvergeStreamsRequest": {
            "target_version": 1,
            "bind_host": "127.0.0.1",
            "advertised_ip": "127.0.0.1",
        },
    }
    assert set(packets) == SUPERVISOR_OMISSIONS
    for name, packet in packets.items():
        _entry_validator(supervisor, name).validate(packet)
    stream = _load("schemas/stream/agent_protocol.json")
    _entry_validator(stream, "AgentHumanInputTakeoverEnvelope").validate(
        {
            "version": "v2",
            "profile_id": "p1",
            "runtime_instance_id": "i1",
            "action": "human_input_takeover",
            "payload": {"input_kind": "key"},
        }
    )


def test_guard_detects_unregistered_wire_model(monkeypatch):
    leaked = type(
        "LeakedAgentEnvelope", (BaseModel,), {"__module__": stream_proto.__name__}
    )
    monkeypatch.setattr(stream_proto, "LeakedAgentEnvelope", leaked, raising=False)
    registered = _registry_names(stream_proto, "GatewayWireMessage")
    with pytest.raises(ProtocolDriftError):
        assert_wire_registry_complete(stream_proto, registered, STREAM_NON_WIRE)


def test_guard_detects_unregistered_supervisor_wire_model(monkeypatch):
    leaked = type(
        "LeakedControlMessage",
        (BaseModel,),
        {"__module__": supervisor_proto.__name__},
    )
    monkeypatch.setattr(
        supervisor_proto, "LeakedControlMessage", leaked, raising=False
    )
    registered = _registry_names(supervisor_proto, "SupervisorMessage")
    with pytest.raises(ProtocolDriftError):
        assert_wire_registry_complete(supervisor_proto, registered, set())


def test_guard_detects_stale_artifact(tmp_path):
    relative = "schemas/runtime/supervisor_protocol.json"
    stale = (ROOT / relative).read_bytes() + b" "
    with pytest.raises(ProtocolDriftError):
        assert_generated_matches_committed(relative, stale, tmp_path)


def test_protocol_artifacts_are_current_and_read_only(tmp_path):
    tracked_before = {
        relative: (ROOT / relative).read_bytes()
        for relative in PROTOCOL_ARTIFACTS
    }
    typescript_before = (ROOT / TYPESCRIPT_ARTIFACT).read_bytes()
    for relative, schema in (
        ("schemas/runtime/supervisor_protocol.json", supervisor_protocol_schema()),
        ("schemas/runtime/agent_protocol.json", agent_protocol_schema()),
        ("schemas/stream/agent_protocol.json", stream_protocol_schema()),
    ):
        rendered = (json.dumps(schema, indent=2) + "\n").encode("utf-8")
        assert_generated_matches_committed(relative, rendered, tmp_path)
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = Path(scratch_dir)
        public = export_openapi_schema(scratch / "cbrowser_v1.json")
        internal = export_openapi_schema(
            scratch / "cbrowser_internal.json", internal=True
        )
        assert_generated_matches_committed(
            "schemas/openapi/cbrowser_v1.json", public.read_bytes(), tmp_path
        )
        assert_generated_matches_committed(
            "schemas/openapi/cbrowser_internal.json",
            internal.read_bytes(),
            tmp_path,
        )
    assert (ROOT / TYPESCRIPT_ARTIFACT).read_bytes() == typescript_before
    for relative, before in tracked_before.items():
        assert (ROOT / relative).read_bytes() == before


def test_backend_contract_change_without_typescript_update_is_detected(tmp_path):
    frontend_root = ROOT / "src/frontend"
    package = json.loads(
        (frontend_root / "package.json").read_text(encoding="utf-8")
    )
    check_api = package["scripts"]["check:api"]
    source_contract = "../../schemas/openapi/cbrowser_v1.json"
    committed_ts = "src/shared/api/generated/cbrowser_v1.d.ts"
    assert "mktemp -d" in check_api
    assert "openapi-typescript" in check_api
    assert source_contract in check_api
    assert "cmp -s" in check_api
    assert committed_ts in check_api
    gate = (ROOT / "scripts/run_gates.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in gate
    assert "npm run check:api --prefix src/frontend" in gate

    cli = frontend_root / "node_modules/.bin/openapi-typescript"
    if not cli.exists():
        pytest.fail(
            "A16 TypeScript drift guard requires openapi-typescript from the "
            "frontend devDependencies; install them with "
            "`npm ci --prefix src/frontend` so "
            "src/frontend/node_modules/.bin/openapi-typescript exists"
        )

    committed = frontend_root / committed_ts
    contract = _load("schemas/openapi/cbrowser_v1.json")
    contract["paths"]["/api/v1/a16_drift_probe"] = {
        "get": {"responses": {"200": {"description": "ok"}}}
    }
    altered_contract = tmp_path / "altered_openapi.json"
    altered_contract.write_text(
        json.dumps(contract, indent=2) + "\n", encoding="utf-8"
    )
    probe = tmp_path / "probe.d.ts"
    subprocess.run(
        ["node", str(cli), str(altered_contract), "-o", str(probe)],
        check=True,
        capture_output=True,
    )
    assert probe.read_bytes() != committed.read_bytes()

    runnable = f'PATH="{cli.parent}:$PATH" && '
    current = subprocess.run(
        ["bash", "-c", runnable + check_api],
        cwd=frontend_root,
        capture_output=True,
        text=True,
    )
    assert current.returncode == 0, current.stderr
    drifted = check_api.replace(source_contract, f'"{altered_contract}"')
    changed = subprocess.run(
        ["bash", "-c", runnable + drifted],
        cwd=frontend_root,
        capture_output=True,
        text=True,
    )
    assert changed.returncode != 0
