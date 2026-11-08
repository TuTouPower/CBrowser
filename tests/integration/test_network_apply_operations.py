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
    supervisor.rebuild_edge = AsyncMock(return_value={"status": "ok"})
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
