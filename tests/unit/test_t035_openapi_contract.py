"""AC-012 regression guards for the exported OpenAPI contract and the absence
of the retired business Tag / embedded-proxy fields.

The export-consistency tests only prove checked-in files match the live app;
these assertions keep a re-introduced ``v1`` group or ``tags``/``proxy`` DTO
field from slipping through a synchronized re-export.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PUBLIC_GROUPS = {
    "artifacts",
    "auth",
    "automation",
    "control",
    "groups",
    "profiles",
    "proxies",
}


def _schema(name: str) -> dict:
    return json.loads(
        (ROOT / "schemas" / "openapi" / name).read_text(encoding="utf-8")
    )


def _groups(schema: dict) -> set[str]:
    return {
        tag
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict)
        for tag in operation.get("tags", [])
    }


def test_public_openapi_groups_are_resource_scoped() -> None:
    groups = _groups(_schema("cbrowser_v1.json"))
    assert groups == PUBLIC_GROUPS
    assert "v1" not in groups


def test_internal_openapi_groups_have_no_v1_group() -> None:
    groups = _groups(_schema("cbrowser_internal.json"))
    assert "v1" not in groups
    assert {"groups", "profiles", "proxies"} <= groups


def test_profile_dtos_have_no_business_tag_or_embedded_proxy() -> None:
    schemas = _schema("cbrowser_v1.json")["components"]["schemas"]
    for name in (
        "ProfileCreateRequest",
        "ProfileUpdateRequest",
        "ProfileResponse",
        "ConfigVersionResponse",
    ):
        props = set(schemas[name].get("properties", {}))
        assert "tags" not in props, name
        assert "proxy" not in props, name


def test_backend_sources_have_no_business_tag_concept() -> None:
    hits = []
    for path in (ROOT / "src" / "backend" / "cbrowser").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "class Tag(" in text or "profile_tags" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []
