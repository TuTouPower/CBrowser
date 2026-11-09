"""Integration tests for Network Apply Operations: lifecycle, failure convergence, and recovery."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cbrowser.adapters.database.models import Base
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    NetworkApplyOperation,
    NetworkApplyPhase,
)
from cbrowser.services.network_service import NetworkService


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.verify_admin_password = AsyncMock(return_value=True)
    return auth


@pytest.mark.asyncio
async def test_apply_operation_full_lifecycle(session_maker, mock_auth, tmp_path):
    repo = ProfileRepository(session_maker)
    supervisor = MagicMock()
    supervisor.rebuild_edge = AsyncMock(
        return_value={"status": "ok", "rebuilt": True}
    )
    supervisor.restore_network_snapshot = AsyncMock(
        return_value={"status": "ok", "restored": 1, "rebuilt": True}
    )
    supervisor.converge_network_streams = AsyncMock(return_value={"status": "ok", "rebuilt_streams": 0})

    svc = NetworkService(
        repo=repo,
        auth_service=mock_auth,
        supervisor_client=supervisor,
        export_dir=tmp_path / "network",
    )

    # 1. Update pending to LAN mode
    await svc.update_pending_config(
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        )
    )

    # 2. Trigger apply
    op = await svc.apply_configuration("correct_password")
    assert op.phase in (NetworkApplyPhase.PENDING, NetworkApplyPhase.REBUILDING_CADDY)

    # 3. Wait for completion
    final_op = await svc.wait_for_operation(op.operation_id, timeout=5.0)
    assert final_op.phase == NetworkApplyPhase.COMPLETED
    assert final_op.error_reason is None

    # P0-1: only a logical resource name crosses the API→Supervisor boundary.
    _, kwargs = supervisor.rebuild_edge.await_args
    assert kwargs["caddyfile_path"] == f"Caddyfile.staging.{op.operation_id}"
    assert "/" not in kwargs["caddyfile_path"]

    # P1-2: the running edge must bind the persistent Caddyfile, so the
    # staging file must be gone while the persistent file remains.
    assert not (tmp_path / "network" / f"Caddyfile.staging.{op.operation_id}").exists()
    assert (tmp_path / "network" / "Caddyfile").is_file()

    # 4. Verify durable persistence in database
    settings = await svc.get_settings()
    assert settings.applied_version.version == 2
    assert settings.applied_version.config.lan_access_enabled
    assert settings.applied_version.config.lan_advertised_ip == "192.168.31.76"
    assert "https://192.168.31.76:56661" in settings.applied_version.origin_whitelist

    # Active operation in DB is cleared on completion
    assert await repo.get_active_network_operation() is None


@pytest.mark.asyncio
async def test_apply_failure_convergence_ac010(session_maker, mock_auth, tmp_path):
    """AC-010: Failure in apply steps converges to FAILED and keeps prior version."""
    repo = ProfileRepository(session_maker)
    supervisor = MagicMock()
    # Inject failure at edge rebuild step
    supervisor.rebuild_edge = AsyncMock(side_effect=RuntimeError("Docker daemon connection lost"))
    supervisor.restore_network_snapshot = AsyncMock(
        return_value={"status": "ok", "restored": 1, "rebuilt": True}
    )

    svc = NetworkService(
        repo=repo,
        auth_service=mock_auth,
        supervisor_client=supervisor,
        export_dir=tmp_path / "network",
    )

    await svc.update_pending_config(
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        )
    )

    op = await svc.apply_configuration("correct_password")
    final_op = await svc.wait_for_operation(op.operation_id, timeout=5.0)

    # Converged to FAILED, error reason recorded
    assert final_op.phase == NetworkApplyPhase.FAILED
    assert "Docker daemon connection lost" in (final_op.error_reason or "")

    # Applied version remains at version 1 (no partial drift)
    settings = await svc.get_settings()
    assert settings.applied_version.version == 1
    assert not settings.applied_version.config.lan_access_enabled

    # Active operation in DB is cleared so future operations are not blocked
    assert await repo.get_active_network_operation() is None


@pytest.mark.asyncio
async def test_rebuild_without_rebuilt_flag_blocks_commit(
    session_maker, mock_auth, tmp_path
):
    """P1-1: rebuilt is not True ( incl. restore_old_entry/not_found ) blocks commit."""
    repo = ProfileRepository(session_maker)
    supervisor = MagicMock()
    supervisor.rebuild_edge = AsyncMock(
        return_value={
            "status": "ok",
            "rebuilt": False,
            "reason": "restore_old_entry",
        }
    )
    supervisor.restore_network_snapshot = AsyncMock(
        return_value={"status": "ok", "restored": 1, "rebuilt": True}
    )
    supervisor.converge_network_streams = AsyncMock(
        return_value={"status": "ok", "rebuilt_streams": 0}
    )
    svc = NetworkService(
        repo=repo,
        auth_service=mock_auth,
        supervisor_client=supervisor,
        export_dir=tmp_path / "network",
    )
    await svc.update_pending_config(
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        )
    )
    op = await svc.apply_configuration("correct_password")
    final_op = await svc.wait_for_operation(op.operation_id, timeout=5.0)
    assert final_op.phase == NetworkApplyPhase.FAILED
    assert "not verified" in (final_op.error_reason or "")
    settings = await svc.get_settings()
    assert settings.applied_version.version == 1
    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.decision == "abort"


@pytest.mark.asyncio
async def test_restore_without_rebuilt_flag_keeps_recovery_incomplete(
    session_maker, mock_auth, tmp_path
):
    """P1-1 (restore path): rebuilt False on restore keeps recovery incomplete."""
    repo = ProfileRepository(session_maker)
    supervisor = MagicMock()
    supervisor.rebuild_edge = AsyncMock(
        side_effect=RuntimeError("Docker daemon connection lost")
    )
    supervisor.restore_network_snapshot = AsyncMock(
        return_value={
            "status": "ok",
            "restored": 0,
            "rebuilt": False,
            "reason": "restore_old_entry",
        }
    )
    svc = NetworkService(
        repo=repo,
        auth_service=mock_auth,
        supervisor_client=supervisor,
        export_dir=tmp_path / "network",
    )
    await svc.update_pending_config(
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        )
    )
    op = await svc.apply_configuration("correct_password")
    await svc.wait_for_operation(op.operation_id, timeout=5.0)
    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.decision == "abort"
    assert txn.recovery_complete is False
    _, kwargs = supervisor.restore_network_snapshot.await_args
    assert kwargs["caddyfile_path"] == "Caddyfile"


@pytest.mark.asyncio
async def test_restore_not_found_is_explicit_terminal(
    session_maker, mock_auth, tmp_path
):
    """P2 not_found way out: missing Caddy is terminal, not permanent spin."""
    repo = ProfileRepository(session_maker)
    supervisor = MagicMock()
    supervisor.rebuild_edge = AsyncMock(
        side_effect=RuntimeError("Docker daemon connection lost")
    )
    supervisor.restore_network_snapshot = AsyncMock(
        return_value={
            "status": "ok",
            "restored": 0,
            "rebuilt": False,
            "reason": "not_found",
            "terminal": True,
        }
    )
    svc = NetworkService(
        repo=repo,
        auth_service=mock_auth,
        supervisor_client=supervisor,
        export_dir=tmp_path / "network",
    )
    await svc.update_pending_config(
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        )
    )
    op = await svc.apply_configuration("correct_password")
    await svc.wait_for_operation(op.operation_id, timeout=5.0)
    txn = await repo.get_network_transaction(op.operation_id)
    assert txn.decision == "abort"
    assert txn.recovery_complete is True
    # Next apply is no longer blocked by the missing edge.
    await svc.update_pending_config(
        NetworkAccessConfig(lan_access_enabled=False)
    )
    op2 = await svc.apply_configuration("correct_password")
    assert op2.operation_id != op.operation_id
