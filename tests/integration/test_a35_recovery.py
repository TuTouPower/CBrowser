"""A35: 网络切换事务全链路与重启恢复（API/SQLite 唯一裁决）。

覆盖：并发拒绝、Gateway 未 ACK 不允许 COMMIT、ABORT 补偿方向、
补偿失败保留现场、密码不落盘/日志、三种重启终局、幂等重放、代次递增。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cbrowser.adapters.database.models import Base, SettingModel
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import (
    NetworkAccessConfig,
    NetworkApplyPhase,
)
from cbrowser.gateway.config import NetworkPublicationAuthority
from cbrowser.services.network_service import NetworkService


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
    return client


def _service(session_maker, supervisor, tmp_path, gateway=None, on_origins_updated=None):
    repo = ProfileRepository(session_maker)
    svc = NetworkService(
        repo=repo,
        auth_service=_auth(),
        supervisor_client=supervisor,
        export_dir=tmp_path / "network",
        gateway=gateway,
        on_origins_updated=on_origins_updated,
    )
    return repo, svc


async def _network_values(session_maker) -> str:
    async with session_maker() as session:
        rows = (
            await session.scalars(
                select(SettingModel.value).where(SettingModel.key.like("network.%"))
            )
        ).all()
    return "\n".join(rows)


def _lan_pending() -> NetworkAccessConfig:
    return NetworkAccessConfig(
        lan_access_enabled=True,
        lan_advertised_ip="192.168.31.76",
        https_port=56661,
    )


@pytest.mark.asyncio
async def test_success_path_commits_via_db_transaction_then_exports(
    session_maker, tmp_path
):
    supervisor = _supervisor()
    repo, svc = _service(session_maker, supervisor, tmp_path)
    await svc.update_pending_config(_lan_pending())

    op = await svc.apply_configuration("admin-password-1")
    final_op = await svc.wait_for_operation(op.operation_id, timeout=5.0)

    assert final_op.phase == NetworkApplyPhase.COMPLETED
    settings = await svc.get_settings()
    assert settings.applied_version.version == 2
    txn = await repo.get_current_network_transaction()
    assert txn.decision == "commit"
    assert txn.transaction_phase == "committed"
    assert txn.execution_generation == 1
    exported = json.loads(
        (tmp_path / "network" / "applied_network_version.json").read_text()
    )
    assert exported["version"] == 2


@pytest.mark.asyncio
async def test_concurrent_apply_is_rejected_by_exclusive_db_registration(
    session_maker, tmp_path
):
    _, svc = _service(session_maker, _supervisor(), tmp_path)
    await svc.update_pending_config(_lan_pending())

    outcomes = await asyncio.gather(
        svc.apply_configuration("pw"),
        svc.apply_configuration("pw"),
        return_exceptions=True,
    )
    errors = [o for o in outcomes if isinstance(o, RuntimeError)]
    successes = [o for o in outcomes if not isinstance(o, BaseException)]
    assert len(errors) == 1
    assert len(successes) == 1
    assert "already in progress" in str(errors[0])


@pytest.mark.asyncio
async def test_gateway_missing_ack_blocks_commit_and_persists_abort(
    session_maker, tmp_path
):
    gateway = MagicMock()
    gateway.authorize = MagicMock(return_value={"authorized": True})
    gateway.acknowledge = MagicMock(return_value={"acked": False})
    gateway.active = MagicMock(return_value=None)
    gateway.revoke = MagicMock(return_value={"revoked": True})

    repo, svc = _service(session_maker, _supervisor(), tmp_path, gateway=gateway)
    await svc.update_pending_config(_lan_pending())
    op = await svc.apply_configuration("pw")
    final_op = await svc.wait_for_operation(op.operation_id, timeout=5.0)

    assert final_op.phase == NetworkApplyPhase.FAILED
    assert (await svc.get_settings()).applied_version.version == 1
    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.decision == "abort"
    assert txn.gateway_acked is False
    assert txn.recovery_complete is True


@pytest.mark.asyncio
async def test_gateway_stale_generation_or_hash_blocks_commit(session_maker, tmp_path):
    gateway = MagicMock()
    gateway.authorize = MagicMock(return_value={"authorized": True})
    gateway.acknowledge = MagicMock(
        return_value={"acked": True, "generation": 999, "snapshot_hash": "stale"}
    )
    gateway.active = MagicMock(
        return_value={"operation_id": "other", "generation": 999, "snapshot_hash": "stale"}
    )
    gateway.revoke = MagicMock(return_value={"revoked": True})

    repo, svc = _service(session_maker, _supervisor(), tmp_path, gateway=gateway)
    await svc.update_pending_config(_lan_pending())
    op = await svc.apply_configuration("pw")
    await svc.wait_for_operation(op.operation_id, timeout=5.0)
    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.decision == "abort"
    assert (await svc.get_settings()).applied_version.version == 1


@pytest.mark.asyncio
async def test_supervisor_disconnect_aborts_and_records_compensation_direction(
    session_maker, tmp_path
):
    supervisor = _supervisor()
    supervisor.rebuild_edge = AsyncMock(
        side_effect=RuntimeError("Docker daemon connection lost")
    )
    repo, svc = _service(session_maker, supervisor, tmp_path)
    await svc.update_pending_config(_lan_pending())

    op = await svc.apply_configuration("pw")
    final_op = await svc.wait_for_operation(op.operation_id, timeout=5.0)

    assert final_op.phase == NetworkApplyPhase.FAILED
    assert "Docker daemon connection lost" in (final_op.error_reason or "")
    assert (await svc.get_settings()).applied_version.version == 1
    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.decision == "abort"
    assert txn.old_applied["version"] == 1
    assert txn.recovery_complete is True
    assert await repo.get_active_network_operation() is None


@pytest.mark.asyncio
async def test_compensation_failure_keeps_recovery_incomplete_and_blocks_next_apply(
    session_maker, tmp_path
):
    gateway = MagicMock()
    gateway.authorize = MagicMock(return_value={"authorized": True})
    gateway.acknowledge = MagicMock(return_value={"acked": False})
    gateway.active = MagicMock(return_value=None)
    gateway.revoke = MagicMock(side_effect=RuntimeError("gateway unreachable"))

    repo, svc = _service(session_maker, _supervisor(), tmp_path, gateway=gateway)
    await svc.update_pending_config(_lan_pending())
    op = await svc.apply_configuration("pw")
    await svc.wait_for_operation(op.operation_id, timeout=5.0)

    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.recovery_complete is False
    assert await repo.get_active_network_operation() is not None
    with pytest.raises(RuntimeError, match="already in progress|recovery"):
        await svc.apply_configuration("pw")


@pytest.mark.asyncio
async def test_commit_publishes_authorized_snapshot_not_mtime_driven(
    session_maker, tmp_path
):
    published: list[list[str]] = []
    authority = NetworkPublicationAuthority()
    authority.import_baseline(
        ["https://127.0.0.1:56661"], generation=0, snapshot_hash="base"
    )
    _, svc = _service(
        session_maker,
        _supervisor(),
        tmp_path,
        gateway=authority,
        on_origins_updated=lambda origins: published.append(list(origins)),
    )
    await svc.update_pending_config(_lan_pending())
    op = await svc.apply_configuration("pw")
    await svc.wait_for_operation(op.operation_id, timeout=5.0)

    assert published
    assert "https://192.168.31.76:56661" in published[-1]
    active = authority.active()
    assert active["operation_id"] == op.operation_id
    assert "https://192.168.31.76:56661" in active["origins"]

    remote = NetworkPublicationAuthority()
    remote.import_baseline(
        ["https://127.0.0.1:56661"], generation=0, snapshot_hash="base"
    )
    assert "https://192.168.31.76:56661" not in remote.active()["origins"]
    remote.authorize(
        active["operation_id"],
        active["generation"],
        active["snapshot_hash"],
        active["origins"],
    )
    assert remote.acknowledge(
        active["operation_id"], active["generation"], active["snapshot_hash"]
    )["acked"] is True
    assert "https://192.168.31.76:56661" in remote.active()["origins"]


@pytest.mark.asyncio
async def test_password_never_persisted_or_logged(
    session_maker, tmp_path, caplog
):
    password = "s3cr3t-admin-password-do-not-store"
    caplog.set_level(logging.DEBUG)
    _, svc = _service(session_maker, _supervisor(), tmp_path)
    await svc.update_pending_config(_lan_pending())

    op = await svc.apply_configuration(password)
    await svc.wait_for_operation(op.operation_id, timeout=5.0)

    assert password not in await _network_values(session_maker)
    assert password not in caplog.text


@pytest.mark.asyncio
async def test_restart_with_commit_finalizes_without_touching_new_instances(
    session_maker, tmp_path
):
    repo, svc = _service(session_maker, _supervisor(), tmp_path)
    await svc.update_pending_config(_lan_pending())
    op = await svc.apply_configuration("pw")
    await svc.wait_for_operation(op.operation_id, timeout=5.0)

    exported = tmp_path / "network" / "applied_network_version.json"
    exported.unlink()

    fresh_supervisor = _supervisor()
    _, restarted = _service(session_maker, fresh_supervisor, tmp_path)
    verdict = await restarted.recover_pending_operation()

    assert verdict == "commit"
    assert exported.is_file()
    assert (await svc.get_settings()).applied_version.version == 2
    fresh_supervisor.rebuild_edge.assert_not_awaited()
    fresh_supervisor.converge_network_streams.assert_not_awaited()
    assert (await repo.get_current_network_transaction()).decision == "commit"


@pytest.mark.asyncio
async def test_idempotent_replay_does_not_bump_version_twice(session_maker, tmp_path):
    repo, svc = _service(session_maker, _supervisor(), tmp_path)
    await svc.update_pending_config(_lan_pending())
    op = await svc.apply_configuration("pw")
    await svc.wait_for_operation(op.operation_id, timeout=5.0)
    first_raw = await _network_values(session_maker)

    _, restarted = _service(session_maker, _supervisor(), tmp_path)
    assert await restarted.recover_pending_operation() == "commit"
    assert await restarted.recover_pending_operation() == "commit"
    settings = await restarted.get_settings()
    assert settings.applied_version.version == 2
    assert await repo.get_current_network_transaction() is not None
    assert await _network_values(session_maker) == first_raw


@pytest.mark.asyncio
async def test_restart_with_abort_restores_old_config(session_maker, tmp_path):
    from cbrowser.domain.models import (
        AppliedNetworkAccessVersion,
        NetworkApplyOperation,
        utc_now_iso,
    )

    repo = ProfileRepository(session_maker)
    old = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        bind_host="127.0.0.1",
        applied_at=utc_now_iso(),
        caddyfile_sha256="old-hash",
        origin_whitelist=["https://127.0.0.1:56661"],
    )
    target = AppliedNetworkAccessVersion(
        version=2,
        config=_lan_pending(),
        bind_host="0.0.0.0",
        applied_at=utc_now_iso(),
        caddyfile_sha256="target-hash",
        origin_whitelist=["https://192.168.31.76:56661"],
    )
    op = NetworkApplyOperation(
        operation_id="op-restart-abort",
        target_version=2,
        phase=NetworkApplyPhase.REBUILDING_CADDY,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    txn = await repo.begin_network_transaction(
        operation=op,
        old_applied=old,
        target_applied=target,
        candidate_hash="target-hash",
    )
    await repo.abort_network_transaction(
        operation_id="op-restart-abort",
        execution_generation=txn.execution_generation,
        reason="crash",
        recovery_complete=False,
    )

    fresh_supervisor = _supervisor()
    _, restarted = _service(session_maker, fresh_supervisor, tmp_path)
    verdict = await restarted.recover_pending_operation()

    assert verdict == "abort"
    assert (await restarted.get_settings()).applied_version.version == 1
    fresh_supervisor.rebuild_edge.assert_not_awaited()
    assert fresh_supervisor.restore_network_snapshot.called
    assert (await repo.get_network_transaction("op-restart-abort")).recovery_complete is True
    assert await repo.get_active_network_operation() is None


@pytest.mark.asyncio
async def test_restart_without_finality_makes_exclusive_abort_decision(
    session_maker, tmp_path
):
    from cbrowser.domain.models import (
        AppliedNetworkAccessVersion,
        NetworkApplyOperation,
        utc_now_iso,
    )

    repo = ProfileRepository(session_maker)
    old = AppliedNetworkAccessVersion(
        version=1,
        config=NetworkAccessConfig(lan_access_enabled=False),
        bind_host="127.0.0.1",
        applied_at=utc_now_iso(),
    )
    op = NetworkApplyOperation(
        operation_id="op-no-finality",
        target_version=2,
        phase=NetworkApplyPhase.VERIFYING_READINESS,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    await repo.begin_network_transaction(
        operation=op,
        old_applied=old,
        target_applied=old.model_copy(update={"version": 2}),
        candidate_hash="h",
    )

    fresh_supervisor = _supervisor()
    _, restarted = _service(session_maker, fresh_supervisor, tmp_path)
    verdict = await restarted.recover_pending_operation()

    assert verdict == "no_finality_abort"
    txn = await repo.get_network_transaction("op-no-finality")
    assert txn.decision == "abort"
    assert (await restarted.get_settings()).applied_version.version == 1
    fresh_supervisor.rebuild_edge.assert_not_awaited()
    assert fresh_supervisor.restore_network_snapshot.called
