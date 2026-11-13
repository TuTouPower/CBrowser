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


def test_openapi_422_is_validation_error_response_not_http_validation_error() -> None:
    """t056_code_f001: the runtime 422 body is the unified shape
    (error/message/details/retryable). The contract must document
    ValidationErrorResponse for every 422, never FastAPI's
    auto-generated HTTPValidationError ({"detail": [...]}): checked
    against the live app (both schema variants) and the checked-in
    exports."""
    for internal in (False, True):
        from cbrowser.api.app import create_app

        label = "internal" if internal else "public"
        schema = create_app(include_internal_schema=internal).openapi()
        _assert_422_is_validation_error_response(schema, label)
        assert "HTTPValidationError" not in json.dumps(schema), label
        assert _validation_error_shape(schema), label
    for name in ("cbrowser_v1.json", "cbrowser_internal.json"):
        text = (ROOT / "schemas" / "openapi" / name).read_text(encoding="utf-8")
        assert "HTTPValidationError" not in text, name
        schema = json.loads(text)
        _assert_422_is_validation_error_response(schema, name)
        assert _validation_error_shape(schema), name


def _assert_422_is_validation_error_response(schema: dict, label: str) -> None:
    refs = []
    for path, methods in schema.get("paths", {}).items():
        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            response_422 = operation.get("responses", {}).get("422")
            if response_422 is None:
                continue
            ref = (
                response_422.get("content", {})
                .get("application/json", {})
                .get("schema", {})
                .get("$ref")
            )
            refs.append(ref)
            assert ref == "#/components/schemas/ValidationErrorResponse", (
                f"{label} {method.upper()} {path}: 422 schema is {ref!r}"
            )
    assert refs, f"{label}: no 422 response found in schema"


def _validation_error_shape(schema: dict) -> bool:
    """ValidationErrorResponse carries the unified shape: a `details`
    list, no legacy `detail` property."""
    props = (
        schema["components"]["schemas"]["ValidationErrorResponse"]
        .get("properties", {})
    )
    return "details" in props and "detail" not in props


def test_backend_sources_have_no_business_tag_concept() -> None:
    hits = []
    for path in (ROOT / "src" / "backend" / "cbrowser").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "class Tag(" in text or "profile_tags" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []
