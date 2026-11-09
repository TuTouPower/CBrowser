"""A35: Supervisor 重建端点消费 X-CBrowser-* header，写执行回执并接 ABORT 补偿。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from cbrowser.network_config import compute_caddyfile_sha256
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import SupervisorCore

TOKEN = "secret-supervisor-token-32-bytes-long!!"


@pytest.fixture
def control_env(tmp_path: Path):
    data_root = tmp_path / "data"
    ops_dir = data_root / "control" / "operations"
    ops_dir.mkdir(parents=True, exist_ok=True)
    network_dir = data_root / "network"
    network_dir.mkdir(parents=True, exist_ok=True)
    validator = MagicMock()
    validator.data_root = data_root
    validator.validate_safe_path = MagicMock(side_effect=lambda p, **_kw: Path(p))
    docker = MagicMock()
    docker.validator = validator
    docker.rebuild_caddy_container = AsyncMock(return_value={"rebuilt": True})
    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=MagicMock(),
        event_forwarder=MagicMock(),
        api_client=MagicMock(),
    )
    token_file = tmp_path / "supervisor_token"
    token_file.write_text(TOKEN, encoding="utf-8")
    token_file.chmod(0o600)
    app = create_control_app(core=core, token_file=token_file)
    client = TestClient(app)
    return core, client, docker, ops_dir, network_dir


def _headers(operation_id: str, generation: int, candidate_hash: str, *, restoring=False):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-CBrowser-Operation-Id": operation_id,
        "X-CBrowser-Execution-Generation": str(generation),
        "X-CBrowser-Candidate-Hash": candidate_hash,
    }
    if restoring:
        headers["X-CBrowser-Restore"] = "1"
    return headers


def _body(resource_name: str):
    return {
        "target_version": 2,
        "bind_host": "0.0.0.0",
        "https_port": 56661,
        "caddyfile_path": resource_name,
    }


def test_headers_produce_verified_journal_receipt(control_env, tmp_path: Path):
    core, client, docker, _ops_dir, network_dir = control_env
    name = "Caddyfile.staging.op-1"
    (network_dir / name).write_text("candidate caddyfile", encoding="utf-8")
    candidate_hash = compute_caddyfile_sha256("candidate caddyfile")

    resp = client.post(
        "/supervisor/v1/network/rebuild-edge",
        json=_body(name),
        headers=_headers("op-1", 3, candidate_hash),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["receipt_verified"] is True
    assert body["operation_id"] == "op-1"
    assert body["execution_generation"] == 3
    assert body["candidate_hash"] == candidate_hash
    docker.rebuild_caddy_container.assert_awaited_once()
    receipt = core.operations.network_execution_receipt("op-1", 3, candidate_hash)
    assert receipt is not None
    assert receipt["status"] == "ok"
    assert receipt["docker_verified"] is True
    assert receipt["operation_id"] == "op-1"
    assert receipt["execution_generation"] == 3
    assert receipt["candidate_hash"] == candidate_hash


def test_missing_headers_do_not_claim_success_receipt(control_env, tmp_path: Path):
    core, client, _docker, ops_dir, network_dir = control_env
    (network_dir / "Caddyfile.staging.op-missing").write_text(
        "candidate caddyfile", encoding="utf-8"
    )

    resp = client.post(
        "/supervisor/v1/network/rebuild-edge",
        json=_body("Caddyfile.staging.op-missing"),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert resp.status_code == 200
    assert resp.json()["receipt_verified"] is False
    assert resp.json()["operation_id"] is None
    assert list(ops_dir.glob("*.json")) == []
    assert core.operations.network_receipt(
        "op-missing",
        "installing",
        "caddy",
        {"operation_id": None, "execution_generation": None, "phase": "installing", "resource": "caddy"},
    ) is None


def test_candidate_hash_mismatch_is_rejected_and_recorded(control_env, tmp_path: Path):
    core, client, docker, _ops_dir, network_dir = control_env
    name = "Caddyfile.staging.op-hash"
    (network_dir / name).write_text("real caddyfile content", encoding="utf-8")
    wrong_hash = "0" * 64

    resp = client.post(
        "/supervisor/v1/network/rebuild-edge",
        json=_body(name),
        headers=_headers("op-hash", 5, wrong_hash),
    )

    assert resp.status_code == 409
    docker.rebuild_caddy_container.assert_not_awaited()
    receipt = core.operations.network_execution_receipt("op-hash", 5, wrong_hash)
    assert receipt is not None
    assert receipt["status"] == "rejected"
    assert receipt["docker_verified"] is False
    assert "hash" in receipt["reason"]


def test_restore_header_routes_to_abort_compensation(control_env, tmp_path: Path):
    core, client, docker, _ops_dir, network_dir = control_env
    (network_dir / "Caddyfile").write_text("old caddyfile", encoding="utf-8")
    candidate_hash = compute_caddyfile_sha256("old caddyfile")

    resp = client.post(
        "/supervisor/v1/network/rebuild-edge",
        json=_body("Caddyfile"),
        headers=_headers("op-abort", 4, candidate_hash, restoring=True),
    )

    assert resp.status_code == 200
    assert resp.json()["restored"] is True
    assert resp.json()["receipt_verified"] is True
    docker.rebuild_caddy_container.assert_awaited_once()
    receipt = core.operations.network_execution_receipt(
        "op-abort", 4, candidate_hash, restoring=True
    )
    assert receipt is not None
    assert receipt["status"] == "ok"
    assert receipt["restoring"] is True
    assert core.operations.network_execution_receipt(
        "op-abort", 4, candidate_hash, restoring=False
    ) is None


def test_generation_bump_does_not_500_on_retry(control_env, tmp_path: Path):
    """P1-A fencing: same operation with bumped generation is a new command.

    Real reproduction for the journal 500: first installing rebuild with
    generation N succeeds 200, then the retry with generation N+1 must
    also succeed 200 instead of raising "Operation ID was already used
    for a different request".
    """
    core, client, docker, _ops_dir, network_dir = control_env
    name = "Caddyfile.staging.op-retry"
    (network_dir / name).write_text("candidate caddyfile", encoding="utf-8")
    candidate_hash = compute_caddyfile_sha256("candidate caddyfile")

    first = client.post(
        "/supervisor/v1/network/rebuild-edge",
        json=_body(name),
        headers=_headers("op-retry", 3, candidate_hash),
    )
    assert first.status_code == 200
    assert first.json()["receipt_verified"] is True

    second = client.post(
        "/supervisor/v1/network/rebuild-edge",
        json=_body(name),
        headers=_headers("op-retry", 4, candidate_hash),
    )
    assert second.status_code == 200
    assert second.json()["receipt_verified"] is True
    assert second.json()["execution_generation"] == 4

    assert (
        core.operations.network_execution_receipt("op-retry", 3, candidate_hash)
        is not None
    )
    assert (
        core.operations.network_execution_receipt("op-retry", 4, candidate_hash)
        is not None
    )
