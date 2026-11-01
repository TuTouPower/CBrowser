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
