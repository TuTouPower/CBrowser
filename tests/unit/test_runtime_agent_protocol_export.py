"""Runtime Agent protocol schema is generated, not hand-maintained."""

import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_exported_runtime_agent_protocol_is_byte_identical():
    export = runpy.run_path(str(ROOT / "scripts/export_runtime_agent_protocol.py"))
    generated = json.dumps(export["agent_protocol_schema"](), indent=2) + "\n"
    checked_in = (ROOT / "schemas/runtime/agent_protocol.json").read_text()
    assert generated == checked_in


def test_public_openapi_excludes_internal_routers():
    from cbrowser.api.app import create_app

    app = create_app()
    paths = set(app.openapi()["paths"])
    assert not any(path.startswith("/api/v1/internal/") for path in paths)
    assert "/api/v1/health" in paths
    assert "/api/v1/profiles" in paths


def test_public_openapi_declares_security_and_reachable_errors():
    from cbrowser.api.app import create_app

    schema = create_app().openapi()
    schemes = schema["components"]["securitySchemes"]
    assert {
        "sessionCookie",
        "csrfHeader",
        "SupervisorServiceBearer",
        "GatewayServiceBearer",
    } <= set(schemes)
    login = schema["paths"]["/api/v1/auth/login"]["post"]
    assert "security" not in login
    profiles = schema["paths"]["/api/v1/profiles"]["post"]
    assert profiles["security"] == [{"sessionCookie": [], "csrfHeader": []}]
    assert {"401", "403", "422", "503"} <= set(profiles["responses"])


def test_internal_openapi_export_matches_checked_in_file():
    from cbrowser.api.app import create_app

    live = create_app(include_internal_schema=True).openapi()
    checked_in = json.loads(
        (ROOT / "schemas/openapi/cbrowser_internal.json").read_text()
    )
    assert live == checked_in
    internal = live["paths"]["/api/v1/internal/supervisor/runtimes/bind"]["post"]
    assert internal["security"] == [{"SupervisorServiceBearer": []}]
    assert {"401", "403", "503"} <= set(internal["responses"])
    gateway = live["paths"]["/api/v1/internal/gateway/profiles/{profile_id}/runtime"][
        "get"
    ]
    assert gateway["security"] == [{"GatewayServiceBearer": []}]
    # t064: the Gateway-relayed viewer-authorize surface is deleted; the
    # session is resolved at the edge resolver instead.
    assert "/api/v1/internal/gateway/viewer-authorize" not in live["paths"]
    edge = live["paths"]["/api/v1/internal/edge/viewer-authorize"]["get"]
    assert edge["security"] == [{"sessionCookie": []}]
    # The edge proof requirement is declared, not implicit: the resolver
    # only answers Caddy's forward_auth, which presents this header.
    edge_params = {(p["name"], p["in"]) for p in edge.get("parameters", [])}
    assert ("X-CBrowser-Edge-Proof", "header") in edge_params
    ingest = live["paths"]["/api/v1/internal/supervisor/artifacts/downloads"]["post"]
    assert ingest["security"] == [{"SupervisorServiceBearer": []}]


def test_supervisor_reporting_routes_are_service_plane_only():
    from cbrowser.api.app import create_app

    public_paths = set(create_app().openapi()["paths"])
    assert "/api/v1/runtimes/bind" not in public_paths
    assert "/api/v1/runtimes/observed" not in public_paths
    assert "/api/v1/runtimes/events" not in public_paths
    internal_paths = set(create_app(include_internal_schema=True).openapi()["paths"])
    assert {
        "/api/v1/internal/supervisor/runtimes/bind",
        "/api/v1/internal/supervisor/runtimes/observed",
        "/api/v1/internal/supervisor/runtimes/events",
    } <= internal_paths


def test_openapi_declares_artifact_and_internal_error_codes():
    from cbrowser.api.app import create_app

    public = create_app().openapi()
    upload = public["paths"]["/api/v1/profiles/{profile_id}/artifacts"]["post"]
    assert {"400", "401", "403", "404", "413", "422", "503", "507"} <= set(
        upload["responses"]
    )
    internal = create_app(include_internal_schema=True).openapi()
    profile = internal["paths"]["/api/v1/internal/supervisor/profiles/{profile_id}"]["get"]
    assert "404" in profile["responses"]
    ingest = internal["paths"][
        "/api/v1/internal/supervisor/artifacts/downloads"
    ]["post"]
    assert "404" in ingest["responses"]
    desired = internal["paths"][
        "/api/v1/internal/supervisor/profiles/{profile_id}/runtime/desired-state"
    ]["patch"]
    assert "409" in desired["responses"]


def test_openapi_declares_rate_limit_and_internal_conflict_codes():
    from cbrowser.api.app import create_app

    public = create_app().openapi()
    assert "429" in public["paths"]["/api/v1/auth/login"]["post"]["responses"]
    internal = create_app(include_internal_schema=True).openapi()
    bind = internal["paths"]["/api/v1/internal/supervisor/runtimes/bind"]["post"]
    assert {"404", "409"} <= set(bind["responses"])


def test_runtime_state_fields_use_domain_enums():
    """AC-007 (A31): HTTP and SSE runtime DTOs only admit domain states."""
    import pytest
    from cbrowser.api.app import create_app
    from cbrowser.domain.models import (
        ProfileRuntimeResponse,
        ProfileRuntimeStatusEvent,
    )
    from pydantic import ValidationError

    schema = create_app().openapi()
    runtime = schema["components"]["schemas"]["ProfileRuntimeResponse"]
    assert set(runtime["properties"]["desired_state"]["enum"]) == {
        "stopped",
        "running",
    }
    assert set(runtime["properties"]["observed_state"]["enum"]) == {
        "stopped",
        "starting",
        "running",
        "stopping",
        "error",
    }
    event = schema["components"]["schemas"]["ProfileRuntimeStatusEvent"]
    assert set(event["properties"]["observed_state"]["enum"]) == {
        "stopped",
        "starting",
        "running",
        "stopping",
        "error",
    }

    base = {
        "profile_id": "p1",
        "desired_state": "stopped",
        "observed_state": "stopped",
        "runtime_instance_id": None,
        "config_version": 1,
        "failure_count": 0,
        "restart_blocked": False,
        "last_exit_event_id": None,
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    with pytest.raises(ValidationError):
        ProfileRuntimeResponse(**{**base, "observed_state": "bogus"})
    with pytest.raises(ValidationError):
        ProfileRuntimeStatusEvent(
            profile_id="p1",
            desired_state="bogus",
            observed_state="stopped",
            updated_at="2026-01-01T00:00:00+00:00",
        )


def test_api_docs_are_closed_by_default(monkeypatch):
    from cbrowser.api.app import create_app

    monkeypatch.delenv("CBROWSER_API_DOCS", raising=False)
    app = create_app()
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_openapi_all_operations_declare_structural_contract_codes():
    from cbrowser.api.app import create_app

    for include_internal, schema in (
        (False, create_app().openapi()),
        (True, create_app(include_internal_schema=True).openapi()),
    ):
        for path, methods in schema["paths"].items():
            if path in {"/api/v1/health", "/api/v1/auth/login"}:
                continue
            for method, operation in methods.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                responses = set(operation.get("responses", {}))
                assert {"401", "403", "503"} <= responses, (path, method, responses)
                if "{" in path:
                    assert "404" in responses, (path, method, responses)
                if method in {"post", "put", "patch", "delete"}:
                    assert "422" in responses, (path, method, responses)
                if "/artifacts" in path and not path.startswith("/api/v1/internal/"):
                    assert {"400", "413", "507"} <= responses, (path, method, responses)


def test_runtime_agent_schema_uses_entry_index_convention():
    """A41: consumers enter via the messages index; no top-level anyOf."""
    import jsonschema
    import pytest

    schema = json.loads((ROOT / "schemas/runtime/agent_protocol.json").read_text())
    assert "anyOf" not in schema
    assert schema["version"] == "2.0.0"
    assert set(schema["messages"]) == {
        "HealthResponse",
        "ConfigVersionResponse",
        "ControlRequest",
        "ControlResponse",
        "RuntimeEventRecord",
        "DownloadEventRecord",
        "RuntimeStateRecord",
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

    entry("ControlRequest").validate({"action": "close"})
    with pytest.raises(jsonschema.ValidationError):
        entry("ControlRequest").validate({"action": "explode"})

    # Every message in the index accepts a minimal valid packet through
    # its own entry point (full coverage, not a sample).
    valid_packets = {
        "HealthResponse": {
            "status": "ok",
            "ready": True,
            "display_ready": True,
            "browser_ready": True,
            "audio_ready": True,
            "cdp_ready": True,
            "profile_id": "p1",
            "runtime_instance_id": "i1",
        },
        "ConfigVersionResponse": {"profile_id": "p1", "runtime_instance_id": "i1"},
        "ControlRequest": {"action": "close"},
        "ControlResponse": {"status": "ok", "action": "close"},
        "RuntimeEventRecord": {
            "event_id": "e1",
            "profile_id": "p1",
            "runtime_instance_id": "i1",
        },
        "DownloadEventRecord": {
            "event_id": "e1",
            "profile_id": "p1",
            "runtime_instance_id": "i1",
            "guid": "g1",
        },
        "RuntimeStateRecord": {
            "profile_id": "p1",
            "runtime_instance_id": "i1",
            "state": "running",
        },
    }
    assert set(valid_packets) == set(schema["messages"])
    for message, packet in valid_packets.items():
        entry(message).validate(packet)


def test_exported_schema_files_end_with_exactly_one_newline():
    for relative in (
        "schemas/runtime/supervisor_protocol.json",
        "schemas/runtime/agent_protocol.json",
        "schemas/stream/agent_protocol.json",
        "schemas/openapi/cbrowser_v1.json",
        "schemas/openapi/cbrowser_internal.json",
    ):
        raw = (ROOT / relative).read_bytes()
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n"), relative
