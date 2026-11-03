"""Internal service surfaces: configuration errors vs credential failures.

AC-004 (A6): a missing Supervisor/Gateway/Artifact configuration reports
``service_not_configured`` with ``retryable=false`` (never the retryable
``database_busy`` shape); missing or wrong service tokens are 401.
AC-007 (A31): Supervisor and Gateway tokens are independent identities.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.api.app import create_app
from fastapi.testclient import TestClient

ORIGIN = "https://app.cbrowser.local"
DOWNLOAD_BODY = {
    "event_id": "evt_cfg_1",
    "profile_id": "prof-x",
    "runtime_instance_id": "inst-x",
    "path": "/exchange/downloads/guid",
    "name": "file.csv",
    "size": 1,
    "sha256": None,
    "content_type": "text/csv",
}


def _make_app(tmp_path: Path, *, with_tokens: bool):
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    admin_file.chmod(0o600)
    kwargs = {}
    tokens = {}
    if with_tokens:
        for name in ("supervisor", "gateway"):
            token = secrets.token_urlsafe(32)
            token_file = tmp_path / f"{name}.token"
            token_file.write_text(token, encoding="utf-8")
            token_file.chmod(0o600)
            kwargs[f"{name}_token_file"] = token_file
            tokens[name] = token
    app = create_app(
        db_path=tmp_path / "svc.db",
        admin_password_file=admin_file,
        allowed_origins=[ORIGIN],
        include_internal_schema=True,
        **kwargs,
    )
    return app, tokens


@pytest.fixture
def unconfigured_client(tmp_path: Path):
    app, _ = _make_app(tmp_path, with_tokens=False)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client


@pytest.fixture
def configured_client(tmp_path: Path):
    app, tokens = _make_app(tmp_path, with_tokens=True)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, tokens


def _assert_service_not_configured(response) -> None:
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "service_not_configured"
    assert body["retryable"] is False


def test_supervisor_surface_unconfigured(unconfigured_client) -> None:
    _assert_service_not_configured(
        unconfigured_client.get("/api/v1/internal/supervisor/health")
    )


def test_gateway_surface_unconfigured(unconfigured_client) -> None:
    _assert_service_not_configured(
        unconfigured_client.post(
            "/api/v1/internal/gateway/viewer-authorize",
            json={
                "session_token": "abc",
                "origin": ORIGIN,
                "profile_id": "prof-x",
            },
        )
    )


def test_artifact_surface_unconfigured(unconfigured_client) -> None:
    _assert_service_not_configured(
        unconfigured_client.post(
            "/api/v1/internal/supervisor/artifacts/downloads",
            json=DOWNLOAD_BODY,
        )
    )


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("patch", "/api/v1/internal/supervisor/profiles/p1/runtime/desired-state", {"desired_state": "running"}),
        ("post", "/api/v1/internal/supervisor/runtimes/bind", {"runtime_instance_id": "i1"}),
        ("post", "/api/v1/internal/supervisor/runtimes/observed", {"runtime_instance_id": "i1", "observed_state": "running"}),
        ("post", "/api/v1/internal/supervisor/runtimes/events", {"event_id": "e1", "profile_id": "p1", "runtime_instance_id": "i1"}),
    ],
)
def test_supervisor_write_endpoints_unconfigured(
    unconfigured_client, method, path, body
) -> None:
    _assert_service_not_configured(
        getattr(unconfigured_client, method)(path, json=body)
    )


def test_wrong_and_missing_tokens_are_401(configured_client) -> None:
    client, tokens = configured_client
    for headers in ({}, {"Authorization": "Bearer wrong-token-value"}):
        response = client.get("/api/v1/internal/supervisor/health", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"] != "service_not_configured"
        response = client.post(
            "/api/v1/internal/gateway/viewer-authorize",
            json={"session_token": "abc", "origin": ORIGIN, "profile_id": "prof-x"},
            headers=headers,
        )
        assert response.status_code == 401


def test_service_tokens_are_independent_identities(configured_client) -> None:
    client, tokens = configured_client
    supervisor = {"Authorization": f"Bearer {tokens['supervisor']}"}
    gateway = {"Authorization": f"Bearer {tokens['gateway']}"}

    # Each token works only on its own surface.
    assert client.get("/api/v1/internal/supervisor/health", headers=supervisor).status_code == 200
    assert client.get("/api/v1/internal/supervisor/health", headers=gateway).status_code == 401
    assert (
        client.post(
            "/api/v1/internal/gateway/viewer-authorize",
            json={"session_token": "abc", "origin": ORIGIN, "profile_id": "prof-x"},
            headers=supervisor,
        ).status_code
        == 401
    )
    viewer = client.post(
        "/api/v1/internal/gateway/viewer-authorize",
        json={"session_token": "abc", "origin": ORIGIN, "profile_id": "prof-x"},
        headers=gateway,
    )
    assert viewer.status_code == 200
    assert viewer.json()["allowed"] is False

    # Artifact ingest rides the Supervisor identity, not the Gateway one.
    assert (
        client.post(
            "/api/v1/internal/supervisor/artifacts/downloads",
            json=DOWNLOAD_BODY,
            headers=gateway,
        ).status_code
        == 401
    )
