from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from cbrowser.api.v1.network_router import create_network_router

ROOT = Path(__file__).resolve().parents[2]


def _response_model(router, path: str, method: str):
    for route in router.routes:
        if (
            getattr(route, "path", None) == path
            and method in getattr(route, "methods", set())
        ):
            return getattr(route, "response_model", None)
    return None


def _schema() -> dict:
    return json.loads(
        (ROOT / "schemas" / "openapi" / "cbrowser_v1.json").read_text(
            encoding="utf-8"
        )
    )


def test_put_settings_response_model_is_named_dto() -> None:
    model = _response_model(
        create_network_router(), "/api/v1/network/settings", "PUT"
    )
    assert isinstance(model, type) and issubclass(model, BaseModel)
    assert model.__name__ == "NetworkSettingsUpdateResponse"
    assert set(model.model_fields) == {"status"}


def test_check_disconnect_response_model_is_named_dto() -> None:
    model = _response_model(
        create_network_router(), "/api/v1/network/check-disconnect", "GET"
    )
    assert isinstance(model, type) and issubclass(model, BaseModel)
    assert model.__name__ == "NetworkDisconnectCheckResponse"
    assert set(model.model_fields) == {"will_disconnect", "new_entry_url"}


def test_exported_schema_references_named_network_response_models() -> None:
    schema = _schema()
    paths = schema["paths"]
    for path, method, expected in (
        ("/api/v1/network/settings", "put", "NetworkSettingsUpdateResponse"),
        (
            "/api/v1/network/check-disconnect",
            "get",
            "NetworkDisconnectCheckResponse",
        ),
    ):
        response = paths[path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response.get("$ref", "").endswith("/" + expected), (path, response)
        assert expected in schema["components"]["schemas"]


def test_network_request_bodies_reference_named_schemas() -> None:
    schema = _schema()
    paths = schema["paths"]
    put_body = paths["/api/v1/network/settings"]["put"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    assert put_body.get("$ref", "").endswith("/NetworkAccessConfig")
    apply_body = paths["/api/v1/network/apply"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    assert apply_body.get("$ref", "").endswith("/NetworkApplyRequest")
