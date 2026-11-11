"""t054 AC-001: the API exposes no network-configuration surface at all.

No /api/v1/network path and no Network* schema may appear in the live
OpenAPI document (nor in the checked-in export, which the existing
schema-match test keeps in sync with the live app).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DELETED_SCHEMAS = (
    "NetworkAccessConfig",
    "AppliedNetworkAccessVersion",
    "NetworkApplyOperation",
    "NetworkAccessSettingsResponse",
    "NetworkApplyRequest",
    "NetworkSettingsUpdateResponse",
    "NetworkDisconnectCheckResponse",
    "NetworkApplyPhase",
)


def test_live_openapi_has_no_network_paths_or_schemas(tmp_path: Path) -> None:
    from cbrowser.api.app import create_app

    app = create_app(db_path=tmp_path / "openapi.db")
    schema = app.openapi()
    paths = set(schema["paths"])
    assert not any(path.startswith("/api/v1/network") for path in paths), (
        sorted(p for p in paths if "network" in p)
    )
    assert not any(path.startswith("/network") for path in paths)
    schemas = set(schema.get("components", {}).get("schemas", {}))
    assert not (set(DELETED_SCHEMAS) & schemas), set(DELETED_SCHEMAS) & schemas


def test_checked_in_openapi_export_has_no_network_paths_or_schemas() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "openapi" / "cbrowser_v1.json").read_text(
            encoding="utf-8"
        )
    )
    paths = set(schema["paths"])
    assert not any(path.startswith("/api/v1/network") for path in paths)
    schemas = set(schema.get("components", {}).get("schemas", {}))
    assert not (set(DELETED_SCHEMAS) & schemas)
    generated = (
        ROOT
        / "src"
        / "frontend"
        / "src"
        / "shared"
        / "api"
        / "generated"
        / "cbrowser_v1.d.ts"
    ).read_text(encoding="utf-8")
    for name in DELETED_SCHEMAS:
        assert name not in generated, name
    assert "/api/v1/network" not in generated
