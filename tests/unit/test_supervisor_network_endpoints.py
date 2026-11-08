"""Unit tests for Supervisor network rebuild endpoints and Stream drift detection."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cbrowser.supervisor.control_server import create_control_app


@pytest.fixture
def mock_supervisor_core():
    core = MagicMock()
    core.rebuild_edge_proxy = AsyncMock(return_value={"status": "ok", "version": 2})
    core.converge_network_streams = AsyncMock(
        return_value={"status": "ok", "rebuilt_streams": 1}
    )
    return core


@pytest.fixture
def supervisor_test_app(mock_supervisor_core, tmp_path):
    token_file = tmp_path / "supervisor_token"
    # minimum 32 bytes secret, 0600 permissions
    token_file.write_text("secret-supervisor-token-32-bytes-long!!")
    token_file.chmod(0o600)

    app = create_control_app(
        core=mock_supervisor_core,
        token_file=token_file,
    )
    return app


def test_rebuild_edge_endpoint_auth(supervisor_test_app):
    client = TestClient(supervisor_test_app)
    # 401 without auth
    resp = client.post(
        "/supervisor/v1/network/rebuild-edge",
        json={
            "target_version": 2,
            "bind_host": "0.0.0.0",
            "https_port": 56661,
            "caddyfile_path": "/data/network/Caddyfile",
        },
    )
    assert resp.status_code == 401

    # 200 with auth
    resp2 = client.post(
        "/supervisor/v1/network/rebuild-edge",
        json={
            "target_version": 2,
            "bind_host": "0.0.0.0",
            "https_port": 56661,
            "caddyfile_path": "/data/network/Caddyfile",
        },
        headers={"Authorization": "Bearer secret-supervisor-token-32-bytes-long!!"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "ok"


def test_converge_streams_endpoint(supervisor_test_app):
    client = TestClient(supervisor_test_app)
    resp = client.post(
        "/supervisor/v1/network/converge-streams",
        json={
            "target_version": 2,
            "bind_host": "0.0.0.0",
            "advertised_ip": "192.168.31.76",
        },
        headers={"Authorization": "Bearer secret-supervisor-token-32-bytes-long!!"},
    )
    assert resp.status_code == 200
    assert resp.json()["rebuilt_streams"] == 1
