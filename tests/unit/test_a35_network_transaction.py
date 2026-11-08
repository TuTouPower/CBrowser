"""A35: API/SQLite 是网络切换配置事务的唯一裁决者。

覆盖：排他登记、执行代次、COMMIT/ABORT 裁决、Gateway ACK 门禁、
幂等重放、旧快照冻结、补偿未完成现场保留、显式空库导入、发布快照授权。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cbrowser.adapters.database.models import Base, SettingModel
from cbrowser.adapters.database.repository import (
    NetworkTransaction,
    ProfileRepository,
)
from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    NetworkApplyOperation,
    NetworkApplyPhase,
    utc_now_iso,
)
from cbrowser.gateway.config import NetworkPublicationAuthority
from cbrowser.network_config import write_applied_network_state


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


def _version(num: int, port: int = 56661) -> AppliedNetworkAccessVersion:
    return AppliedNetworkAccessVersion(
        version=num,
        config=NetworkAccessConfig(lan_access_enabled=False, https_port=port),
        bind_host="127.0.0.1",
        applied_at=utc_now_iso(),
        caddyfile_sha256=f"hash-{num}",
        origin_whitelist=[f"https://127.0.0.1:{port}"],
    )


def _op(op_id: str, target: int = 2) -> NetworkApplyOperation:
    return NetworkApplyOperation(
        operation_id=op_id,
        target_version=target,
        phase=NetworkApplyPhase.PENDING,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )


async def _settings_value(session_maker, key: str) -> str | None:
    async with session_maker() as session:
        row = await session.get(SettingModel, key)
        return row.value if row is not None else None


@pytest.mark.asyncio
async def test_begin_is_exclusive_and_rejects_concurrent_operation(session_maker):
    repo = ProfileRepository(session_maker)
    txn = await repo.begin_network_transaction(
        operation=_op("op-a"),
        old_applied=_version(1),
        target_applied=_version(2),
        candidate_hash="candidate-a",
    )
    assert txn.decision == "pending"
    assert txn.execution_generation == 1

    with pytest.raises(RuntimeError, match="already in progress"):
        await repo.begin_network_transaction(
            operation=_op("op-b"),
            old_applied=_version(1),
            target_applied=_version(2),
            candidate_hash="candidate-b",
        )


@pytest.mark.asyncio
async def test_execution_generation_increments_across_begin_abort_and_next_begin(
    session_maker,
):
    repo = ProfileRepository(session_maker)
    first = await repo.begin_network_transaction(
        operation=_op("op-1"),
        old_applied=_version(1),
        target_applied=_version(2),
        candidate_hash="h1",
    )
    aborted = await repo.abort_network_transaction(
        operation_id="op-1",
        execution_generation=first.execution_generation,
        reason="test",
        recovery_complete=True,
    )
    assert aborted.execution_generation > first.execution_generation

    second = await repo.begin_network_transaction(
        operation=_op("op-2"),
        old_applied=_version(1),
        target_applied=_version(2),
        candidate_hash="h2",
    )
    assert second.execution_generation > aborted.execution_generation
    assert await repo.get_execution_generation() == second.execution_generation


@pytest.mark.asyncio
async def test_commit_requires_verifiable_gateway_ack(session_maker):
    repo = ProfileRepository(session_maker)
    txn = await repo.begin_network_transaction(
        operation=_op("op-ack"),
        old_applied=_version(1),
        target_applied=_version(2),
        candidate_hash="h-ack",
    )
    with pytest.raises(RuntimeError, match="Gateway ACK"):
        await repo.commit_network_transaction(
            operation_id="op-ack",
            execution_generation=txn.execution_generation,
            gateway_generation=txn.execution_generation,
            gateway_hash="h-ack",
        )
    settings = await repo.get_network_access_settings()
    assert settings.applied_version.version == 1


@pytest.mark.asyncio
async def test_commit_is_idempotent_no_double_version_bump(session_maker):
    repo = ProfileRepository(session_maker)
    txn = await repo.begin_network_transaction(
        operation=_op("op-commit"),
        old_applied=_version(1),
        target_applied=_version(2),
        candidate_hash="h-commit",
    )
    await repo.advance_network_transaction(
        "op-commit",
        gateway_acked=True,
        gateway_generation=txn.execution_generation,
        gateway_hash="h-commit",
    )
    committed = await repo.commit_network_transaction(
        operation_id="op-commit",
        execution_generation=txn.execution_generation,
        gateway_generation=txn.execution_generation,
        gateway_hash="h-commit",
    )
    assert committed.decision == "commit"
    applied_raw = await _settings_value(session_maker, repo.KEY_NETWORK_APPLIED)
    assert '"version":2' in applied_raw

    replayed = await repo.commit_network_transaction(
        operation_id="op-commit",
        execution_generation=txn.execution_generation,
        gateway_generation=txn.execution_generation,
        gateway_hash="h-commit",
    )
    assert replayed.execution_generation == committed.execution_generation
    assert await _settings_value(session_maker, repo.KEY_NETWORK_APPLIED) == applied_raw
    settings = await repo.get_network_access_settings()
    assert settings.applied_version.version == 2


@pytest.mark.asyncio
async def test_abort_freezes_old_snapshot_and_keeps_config_on_old_version(
    session_maker,
):
    repo = ProfileRepository(session_maker)
    old = _version(1)
    txn = await repo.begin_network_transaction(
        operation=_op("op-abort"),
        old_applied=old,
        target_applied=_version(2),
        candidate_hash="h-abort",
    )
    aborted = await repo.abort_network_transaction(
        operation_id="op-abort",
        execution_generation=txn.execution_generation,
        reason="compensate",
        recovery_complete=True,
    )
    assert aborted.decision == "abort"
    assert aborted.old_applied["version"] == 1
    assert aborted.target_applied["version"] == 2
    settings = await repo.get_network_access_settings()
    assert settings.applied_version.version == 1
    assert await repo.get_active_network_operation() is None


@pytest.mark.asyncio
async def test_incomplete_compensation_blocks_next_operation_and_keeps_site(
    session_maker,
):
    repo = ProfileRepository(session_maker)
    txn = await repo.begin_network_transaction(
        operation=_op("op-incomplete"),
        old_applied=_version(1),
        target_applied=_version(2),
        candidate_hash="h-incomplete",
    )
    aborted = await repo.abort_network_transaction(
        operation_id="op-incomplete",
        execution_generation=txn.execution_generation,
        reason="compensation failed",
        recovery_complete=False,
    )
    assert aborted.recovery_complete is False
    assert await repo.get_active_network_operation() is not None
    with pytest.raises(RuntimeError, match="already in progress|recovery"):
        await repo.begin_network_transaction(
            operation=_op("op-next"),
            old_applied=_version(1),
            target_applied=_version(2),
            candidate_hash="h-next",
        )


@pytest.mark.asyncio
async def test_initialize_from_disk_only_when_db_empty(session_maker, tmp_path):
    repo = ProfileRepository(session_maker)
    net_dir = tmp_path / "network"
    write_applied_network_state(net_dir, _version(3), "caddy-v3")

    assert await repo.initialize_network_from_disk(net_dir) is True
    assert (await repo.get_network_access_settings()).applied_version.version == 3

    write_applied_network_state(net_dir, _version(7), "caddy-v7")
    assert await repo.initialize_network_from_disk(net_dir) is False
    assert (await repo.get_network_access_settings()).applied_version.version == 3


@pytest.mark.asyncio
async def test_network_settings_rows_are_the_only_place_for_recovery_fields(
    session_maker,
):
    repo = ProfileRepository(session_maker)
    await repo.begin_network_transaction(
        operation=_op("op-storage"),
        old_applied=_version(1),
        target_applied=_version(2),
        candidate_hash="h-storage",
    )
    async with session_maker() as session:
        keys = (await session.scalars(select(SettingModel.key))).all()
    operation_keys = [k for k in keys if k.startswith("network.operation.")]
    assert operation_keys == [f"{repo.KEY_NETWORK_OP_PREFIX}op-storage"]
    raw = await _settings_value(session_maker, operation_keys[0])
    record = NetworkTransaction.model_validate_json(raw)
    assert record.decision == "pending"
    assert "password" not in raw.lower()
    assert "secret" not in raw.lower()


def test_gateway_mtime_is_only_a_reread_hint_not_switch_proof():
    authority = NetworkPublicationAuthority()
    authority.import_baseline(["https://127.0.0.1:56661"], generation=0, snapshot_hash="base")
    before = authority.active()
    authority.note_mtime(12345.0)
    assert authority.active() == before
    assert authority.acknowledge("op-x", 1, "candidate")["acked"] is False


def test_gateway_ack_requires_authorized_publication_matching_generation_and_hash():
    authority = NetworkPublicationAuthority()
    authority.import_baseline(["https://127.0.0.1:56661"], generation=0, snapshot_hash="base")
    authority.authorize("op-x", 4, "candidate-hash", ["https://127.0.0.1:56661", "https://lan:56661"])
    assert authority.acknowledge("op-x", 3, "candidate-hash")["acked"] is False
    assert authority.acknowledge("op-x", 4, "wrong-hash")["acked"] is False
    ack = authority.acknowledge("op-x", 4, "candidate-hash")
    assert ack["acked"] is True
    active = authority.active()
    assert active["operation_id"] == "op-x"
    assert active["generation"] == 4
    assert active["snapshot_hash"] == "candidate-hash"
    assert "https://lan:56661" in active["origins"]


def test_gateway_revoke_restores_previously_acknowledged_origins():
    authority = NetworkPublicationAuthority()
    authority.import_baseline(["https://127.0.0.1:56661"], generation=0, snapshot_hash="base")
    authority.authorize("op-x", 1, "candidate", ["https://lan:56661"])
    authority.acknowledge("op-x", 1, "candidate")
    assert authority.active()["origins"] == ["https://lan:56661"]
    revoke = authority.revoke("op-x")
    assert revoke["revoked"] is True
    assert authority.active()["origins"] == ["https://127.0.0.1:56661"]
    assert authority.active()["operation_id"] == "baseline"


def test_journal_network_receipts_are_resource_scoped_and_not_a_global_decision(
    tmp_path: Path,
):
    from cbrowser.supervisor.operation_journal import OperationJournal

    journal = OperationJournal(tmp_path)
    request = {"operation_id": "op-1", "generation": 3}
    journal.complete_network_receipt(
        "op-1",
        "installing",
        "caddy",
        request,
        {"status": "ok", "docker_verified": True, "caddyfile_sha256": "h"},
    )
    assert journal.network_receipt("op-1", "installing", "caddy", request)["status"] == "ok"
    assert journal.network_receipt("op-1", "verifying", "caddy", request) is None
    assert journal.network_receipt_verified("op-1", "installing", "caddy", request) is True

    journal.complete_network_receipt(
        "op-1", "verifying", "gateway", request, {"status": "ok"}
    )
    assert journal.network_receipt_verified("op-1", "verifying", "gateway", request) is False
    with pytest.raises(ValueError, match="different request"):
        journal.network_receipt(
            "op-1", "installing", "caddy", {"operation_id": "op-2"}
        )


def _caddy_adapter(run_side_effect):
    from unittest.mock import MagicMock

    from cbrowser.supervisor.docker_adapter import DockerAdapter

    adapter = object.__new__(DockerAdapter)
    adapter.resource_prefix = "cbrowser"
    client = MagicMock()
    old_container = MagicMock()
    old_container.id = "old-id"
    client.containers.get.return_value = old_container
    client.api.inspect_container.return_value = {
        "Config": {"Image": "sha256:abc", "Env": [], "Labels": {}},
        "HostConfig": {
            "PortBindings": {
                "443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "56661"}]
            },
            "Binds": [],
        },
        "NetworkSettings": {"Networks": {"cbrowser-edge": {}}},
    }
    client.containers.run.side_effect = run_side_effect
    adapter.client = client
    return adapter, client


@pytest.mark.asyncio
async def test_caddy_rebuild_failure_restores_old_entry():
    from unittest.mock import MagicMock

    from docker.errors import DockerException

    restored = MagicMock()
    restored.id = "restored-id"
    adapter, client = _caddy_adapter([DockerException("boom"), restored])

    result = await adapter.rebuild_caddy_container(
        bind_host="0.0.0.0",
        https_port=58888,
        caddyfile_path="/x/Caddyfile",
    )

    assert result["rebuilt"] is False
    assert result["old_entry_preserved"] is True
    assert result["reason"] == "restore_old_entry"
    assert client.containers.run.call_args_list[1].kwargs["ports"] == {
        "443/tcp": ("127.0.0.1", 56661)
    }


@pytest.mark.asyncio
async def test_caddy_rebuild_restore_failure_keeps_site_unreleased():
    from docker.errors import DockerException

    from cbrowser.supervisor.docker_adapter import DockerSandboxError

    adapter, _ = _caddy_adapter(DockerException("boom"))
    with pytest.raises(DockerSandboxError, match="old entry could not be restored"):
        await adapter.rebuild_caddy_container(
            bind_host="0.0.0.0",
            https_port=58888,
            caddyfile_path="/x/Caddyfile",
        )
