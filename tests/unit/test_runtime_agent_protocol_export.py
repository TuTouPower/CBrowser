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
    assert {"sessionCookie", "csrfHeader", "serviceBearer"} <= set(schemes)
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
    assert internal["security"] == [{"serviceBearer": []}]
    assert {"401", "403", "503"} <= set(internal["responses"])


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
