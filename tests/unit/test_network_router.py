"""Unit tests for Network API endpoints."""

import os
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cbrowser.adapters.database.models import SessionModel
from cbrowser.api.v1.network_router import create_network_router
from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    NetworkAccessSettingsResponse,
    NetworkApplyOperation,
    NetworkApplyPhase,
)


@pytest.fixture
def mock_network_service():
    svc = MagicMock()
    # Default settings
    settings = NetworkAccessSettingsResponse(
        pending_config=NetworkAccessConfig(lan_access_enabled=False),
        applied_version=AppliedNetworkAccessVersion(
            version=1,
            config=NetworkAccessConfig(lan_access_enabled=False),
            applied_at="2026-11-08T00:00:00+08:00",
            caddyfile_sha256="",
            origin_whitelist=["https://127.0.0.1:56661"],
        ),
        active_operation=None,
    )
    svc.get_settings = AsyncMock(return_value=settings)
    svc.update_pending_config = AsyncMock()

    op = NetworkApplyOperation(
        operation_id="test-op-123",
        target_version=2,
        phase=NetworkApplyPhase.PENDING,
        created_at="2026-11-08T00:00:00+08:00",
        updated_at="2026-11-08T00:00:00+08:00",
    )
    svc.apply_configuration = AsyncMock(return_value=op)
    svc.get_operation = AsyncMock(return_value=op)
    svc.check_entry_disconnect = MagicMock(return_value=(False, "https://127.0.0.1:56661"))
    return svc


@pytest.fixture
def test_app(mock_network_service, tmp_path):
    app = FastAPI()
    app.state.network_service = mock_network_service
    app.state.allowed_origins = ["https://127.0.0.1:56661", "https://localhost:56661"]

    # Mock auth service
    auth_service = MagicMock()
    valid_session = SessionModel(
        id="s1",
        token_hash="valid-hash",
        csrf_token="csrf-secret",
        expires_at="2099-01-01T00:00:00+08:00",
    )
    auth_service.get_valid_session = AsyncMock(return_value=valid_session)
    app.state.auth_service = auth_service
    app.state.caddy_ca_dir = tmp_path

    router = create_network_router()
    app.include_router(router)
    return app


def test_get_settings_unauthenticated(test_app):
    client = TestClient(test_app)
    resp = client.get("/api/v1/network/settings")
    assert resp.status_code == 401


def test_get_settings_authenticated(test_app, mock_network_service):
    client = TestClient(test_app, cookies={"cbrowser_session": "valid-token"})
    resp = client.get("/api/v1/network/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "pending_config" in data
    assert "applied_version" in data
    assert data["applied_version"]["version"] == 1


def test_put_settings_csrf_and_origin(test_app, mock_network_service):
    client = TestClient(test_app, cookies={"cbrowser_session": "valid-token"})
    payload = {"lan_access_enabled": True, "lan_advertised_ip": "192.168.31.76"}

    # Missing CSRF
    resp1 = client.put(
        "/api/v1/network/settings",
        json=payload,
        headers={"origin": "https://127.0.0.1:56661"},
    )
    assert resp1.status_code == 403

    # Disallowed Origin
    resp2 = client.put(
        "/api/v1/network/settings",
        json=payload,
        headers={"origin": "https://evil.com", "x-csrf-token": "csrf-secret"},
    )
    assert resp2.status_code == 403

    # Success
    resp3 = client.put(
        "/api/v1/network/settings",
        json=payload,
        headers={"origin": "https://127.0.0.1:56661", "x-csrf-token": "csrf-secret"},
    )
    assert resp3.status_code == 200
    mock_network_service.update_pending_config.assert_awaited_once()


def test_apply_configuration_endpoint(test_app, mock_network_service):
    client = TestClient(test_app, cookies={"cbrowser_session": "valid-token"})

    resp = client.post(
        "/api/v1/network/apply",
        json={"admin_password": "correct_password"},
        headers={"origin": "https://127.0.0.1:56661", "x-csrf-token": "csrf-secret"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["operation_id"] == "test-op-123"
    assert data["target_version"] == 2


def test_get_operation_endpoint(test_app):
    client = TestClient(test_app, cookies={"cbrowser_session": "valid-token"})
    resp = client.get("/api/v1/network/operations/test-op-123")
    assert resp.status_code == 200
    assert resp.json()["operation_id"] == "test-op-123"


def test_root_ca_download(test_app, tmp_path):
    client = TestClient(test_app)
    # 404 when file does not exist
    resp = client.get("/api/v1/network/root-ca")
    assert resp.status_code == 404

    # Create root.crt (public key only)
    ca_file = tmp_path / "root.crt"
    ca_file.write_text("-----BEGIN CERTIFICATE-----\nMIIB...PUBLIC\n-----END CERTIFICATE-----")

    resp2 = client.get("/api/v1/network/root-ca")
    assert resp2.status_code == 200
    assert "BEGIN CERTIFICATE" in resp2.text
    assert resp2.headers["content-type"].startswith("application/x-x509-ca-cert") or resp2.headers["content-type"].startswith("text/plain")
