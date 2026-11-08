"""A35: Gateway 进程内授权快照与跨进程 ACK 回执，COMMIT 不由 API 进程自证。"""

from __future__ import annotations

import secrets
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from aiohttp.test_utils import TestServer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cbrowser.adapters.database.models import Base
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    NetworkApplyPhase,
    utc_now_iso,
)
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app
from cbrowser.network_config import write_applied_network_state
from cbrowser.services.network_service import GatewayPublicationClient, NetworkService

BASELINE_ORIGIN = "https://127.0.0.1:56661"
CANDIDATE_ORIGIN = "https://192.168.31.76:56661"


class _StubApi:
    async def authorize_viewer(self, *args, **kwargs):
        return True, None

    async def get_profile_runtime(self, *args, **kwargs):
        return None

    async def report_human_takeover(self, *args, **kwargs):
        return {}

    async def close(self):
        return None


@pytest_asyncio.fixture
async def gateway_env(tmp_path: Path):
    key = tmp_path / "key.txt"
    key.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    key.chmod(0o600)
    net_dir = tmp_path / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    v1 = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        bind_host="127.0.0.1",
        applied_at=utc_now_iso(),
        caddyfile_sha256="hash1",
        origin_whitelist=[BASELINE_ORIGIN],
    )
    write_applied_network_state(net_dir, v1, "caddyfile v1")
    config = GatewayConfig(
        agent_key_file=key,
        gateway_token_file=key,
        api_url="http://127.0.0.1:8000",
        api_token_file=key,
        network_state_dir=net_dir,
    )
    app = create_gateway_app(config, api_client=_StubApi())
    server = TestServer(app)
    await server.start_server()
    base_url = str(server.make_url("/")).rstrip("/")
    token = key.read_text(encoding="utf-8").strip()
    yield config, base_url, token
    await server.close()


def _client(base_url: str, token: str) -> GatewayPublicationClient:
    return GatewayPublicationClient(base_url=base_url, token=token)


@pytest.mark.asyncio
async def test_prepare_receipt_is_from_gateway_process_and_carries_identity(gateway_env):
    config, base_url, token = gateway_env
    client = _client(base_url, token)

    receipt = await client.prepare("op-1", 1, "candidate-hash", [CANDIDATE_ORIGIN])

    assert receipt["source"] == "gateway"
    assert receipt["operation_id"] == "op-1"
    assert receipt["generation"] == 1
    assert receipt["config_hash"] == "candidate-hash"
    assert receipt["published"] is True
    assert CANDIDATE_ORIGIN not in config.allowed_origins
    assert config.active_publication()["operation_id"] == "baseline"


@pytest.mark.asyncio
async def test_acknowledge_switches_gateway_process_origins_and_revoke_restores(gateway_env):
    config, base_url, token = gateway_env
    client = _client(base_url, token)
    await client.prepare("op-1", 1, "candidate-hash", [CANDIDATE_ORIGIN])

    ack = await client.acknowledge("op-1", 1, "candidate-hash")

    assert ack["acked"] is True
    assert ack["source"] == "gateway"
    assert ack["operation_id"] == "op-1"
    assert ack["generation"] == 1
    assert ack["snapshot_hash"] == "candidate-hash"
    assert ack["active"]["operation_id"] == "op-1"
    assert CANDIDATE_ORIGIN in config.allowed_origins
    assert BASELINE_ORIGIN not in config.allowed_origins

    revoked = await client.revoke("op-1", 1, "candidate-hash")
    assert revoked["source"] == "gateway"
    assert BASELINE_ORIGIN in config.allowed_origins
    assert CANDIDATE_ORIGIN not in config.allowed_origins


@pytest.mark.asyncio
async def test_unauthorized_publication_is_rejected_by_gateway(gateway_env):
    _config, base_url, token = gateway_env
    client = _client(base_url, "wrong-token")
    with pytest.raises(RuntimeError, match="Gateway publication"):
        await client.prepare("op-1", 1, "candidate-hash", [CANDIDATE_ORIGIN])


@pytest.mark.asyncio
async def test_stale_ack_or_unprepared_ack_does_not_switch_origins(gateway_env):
    config, base_url, token = gateway_env
    client = _client(base_url, token)

    with pytest.raises(RuntimeError, match="Gateway publication"):
        await client.acknowledge("op-unprepared", 1, "candidate-hash")
    assert CANDIDATE_ORIGIN not in config.allowed_origins

    await client.prepare("op-2", 3, "hash-2", [CANDIDATE_ORIGIN])
    with pytest.raises(RuntimeError, match="Gateway publication"):
        await client.acknowledge("op-2", 2, "hash-2")
    assert CANDIDATE_ORIGIN not in config.allowed_origins


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


def _auth() -> MagicMock:
    auth = MagicMock()
    auth.verify_admin_password = AsyncMock(return_value=True)
    return auth


def _supervisor() -> MagicMock:
    client = MagicMock()
    client.rebuild_edge = AsyncMock(return_value={"status": "ok"})
    client.converge_network_streams = AsyncMock(
        return_value={"status": "ok", "rebuilt_streams": 0}
    )
    client.restore_network_snapshot = AsyncMock(return_value={"status": "ok"})
    return client


class StaleAckClient(GatewayPublicationClient):
    async def acknowledge(self, operation_id, generation, config_hash):
        return await super().acknowledge(operation_id, generation + 1, config_hash)


def _service(session_maker, tmp_path, gateway_client, on_origins_updated=None):
    repo = ProfileRepository(session_maker)
    svc = NetworkService(
        repo=repo,
        auth_service=_auth(),
        supervisor_client=_supervisor(),
        export_dir=tmp_path / "network",
        gateway_client=gateway_client,
        on_origins_updated=on_origins_updated,
    )
    return repo, svc


def _lan_pending() -> NetworkAccessConfig:
    return NetworkAccessConfig(
        lan_access_enabled=True,
        lan_advertised_ip="192.168.31.76",
        https_port=56661,
    )


@pytest.mark.asyncio
async def test_commit_consumes_gateway_process_receipt(session_maker, tmp_path, gateway_env):
    config, base_url, token = gateway_env
    published: list[list[str]] = []
    repo, svc = _service(
        session_maker,
        tmp_path,
        _client(base_url, token),
        on_origins_updated=lambda origins: published.append(list(origins)),
    )
    await svc.update_pending_config(_lan_pending())

    op = await svc.apply_configuration("pw")
    final_op = await svc.wait_for_operation(op.operation_id, timeout=8.0)

    assert final_op.phase == NetworkApplyPhase.COMPLETED
    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.decision == "commit"
    assert txn.gateway_acked is True
    assert CANDIDATE_ORIGIN in config.allowed_origins
    assert CANDIDATE_ORIGIN in published[-1]


@pytest.mark.asyncio
async def test_mismatched_gateway_receipt_blocks_commit_and_revokes_candidate(
    session_maker, tmp_path, gateway_env
):
    config, base_url, token = gateway_env
    client = StaleAckClient(base_url=base_url, token=token)
    repo, svc = _service(session_maker, tmp_path, client)
    await svc.update_pending_config(_lan_pending())

    op = await svc.apply_configuration("pw")
    final_op = await svc.wait_for_operation(op.operation_id, timeout=8.0)

    assert final_op.phase == NetworkApplyPhase.FAILED
    assert (await svc.get_settings()).applied_version.version == 1
    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.decision == "abort"
    assert txn.gateway_acked is False
    assert CANDIDATE_ORIGIN not in config.allowed_origins
    assert BASELINE_ORIGIN in config.allowed_origins


@pytest.mark.asyncio
async def test_gateway_unreachable_blocks_commit(session_maker, tmp_path, gateway_env):
    _config, base_url, token = gateway_env
    client = GatewayPublicationClient(base_url=base_url, token="wrong-token")
    repo, svc = _service(session_maker, tmp_path, client)
    await svc.update_pending_config(_lan_pending())

    op = await svc.apply_configuration("pw")
    final_op = await svc.wait_for_operation(op.operation_id, timeout=8.0)

    assert final_op.phase == NetworkApplyPhase.FAILED
    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.decision == "abort"
    assert txn.gateway_acked is False
