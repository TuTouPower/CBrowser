"""Unit tests for NetworkService: state transitions, idempotency, and recovery."""

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
def mock_auth_service():
    auth = MagicMock()
    # verify_admin_password returns True for 'correct_pw', False otherwise
    async def verify(pw):
        return pw == "correct_pw"
    auth.verify_admin_password = AsyncMock(side_effect=verify)
    return auth


@pytest.fixture
def mock_supervisor_client():
    client = MagicMock()
    client.rebuild_edge = AsyncMock(return_value={"status": "ok"})
    client.converge_network_streams = AsyncMock(return_value={"status": "ok", "rebuilt_streams": 0})
    return client


@pytest.mark.asyncio
async def test_network_service_save_pending_only(session_maker, mock_auth_service, mock_supervisor_client, tmp_path):
    repo = ProfileRepository(session_maker)
    svc = NetworkService(
        repo=repo,
        auth_service=mock_auth_service,
        supervisor_client=mock_supervisor_client,
        export_dir=tmp_path,
    )

    # 1. Initial state
    settings = await svc.get_settings()
    assert not settings.pending_config.lan_access_enabled
    assert settings.applied_version.version == 1

    # 2. Save pending
    new_pending = NetworkAccessConfig(
        lan_access_enabled=True,
        lan_advertised_ip="192.168.31.76",
    )
    await svc.update_pending_config(new_pending)

    # Verify pending changed, applied stayed at version 1 (AC-001, AC-002)
    settings2 = await svc.get_settings()
    assert settings2.pending_config.lan_access_enabled
    assert settings2.pending_config.lan_advertised_ip == "192.168.31.76"
    assert settings2.applied_version.version == 1
    assert not settings2.applied_version.config.lan_access_enabled


@pytest.mark.asyncio
async def test_network_service_apply_lifecycle(session_maker, mock_auth_service, mock_supervisor_client, tmp_path):
    repo = ProfileRepository(session_maker)
    svc = NetworkService(
        repo=repo,
        auth_service=mock_auth_service,
        supervisor_client=mock_supervisor_client,
        export_dir=tmp_path,
    )

    # Update pending to LAN mode
    await svc.update_pending_config(
        NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        )
    )

    # Wrong password raises PermissionError
    with pytest.raises(PermissionError, match="Invalid admin password"):
        await svc.apply_configuration("wrong_pw")

    # Correct password triggers apply operation
    op = await svc.apply_configuration("correct_pw")
    assert op.operation_id
    assert op.target_version == 2

    # Await background apply execution
    await svc.wait_for_operation(op.operation_id, timeout=3.0)

    # Verify completed
    final_op = await svc.get_operation(op.operation_id)
    assert final_op.phase == NetworkApplyPhase.COMPLETED
    assert final_op.error_reason is None

    # Verify applied version is now version 2
    settings = await svc.get_settings()
    assert settings.applied_version.version == 2
    assert settings.applied_version.config.lan_access_enabled
    assert settings.applied_version.config.lan_advertised_ip == "192.168.31.76"

    # Verify Supervisor calls
    mock_supervisor_client.rebuild_edge.assert_awaited_once()
    mock_supervisor_client.converge_network_streams.assert_awaited_once()


@pytest.mark.asyncio
async def test_network_service_concurrency_rejected(session_maker, mock_auth_service, mock_supervisor_client, tmp_path):
    repo = ProfileRepository(session_maker)
    svc = NetworkService(
        repo=repo,
        auth_service=mock_auth_service,
        supervisor_client=mock_supervisor_client,
        export_dir=tmp_path,
    )

    # Simulate an active ongoing operation
    ongoing_op = NetworkApplyOperation(
        operation_id="active-1",
        target_version=2,
        phase=NetworkApplyPhase.REBUILDING_CADDY,
        created_at="2026-11-08T05:00:00+08:00",
        updated_at="2026-11-08T05:00:00+08:00",
    )
    await repo.save_network_operation(ongoing_op)

    # Attempting to apply again raises RuntimeError (AC-003)
    with pytest.raises(RuntimeError, match="Apply operation already in progress"):
        await svc.apply_configuration("correct_pw")
