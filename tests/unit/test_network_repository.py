"""Unit tests for Network Settings and Apply Operation repository persistence."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cbrowser.adapters.database.models import Base
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    NetworkApplyOperation,
    NetworkApplyPhase,
)


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_network_settings_defaults_and_pending_save(session_maker):
    repo = ProfileRepository(session_maker)

    # 1. Defaults
    resp = await repo.get_network_access_settings()
    assert not resp.pending_config.lan_access_enabled
    assert resp.pending_config.lan_advertised_ip is None
    assert resp.applied_version.version == 1
    assert not resp.applied_version.config.lan_access_enabled
    assert resp.active_operation is None

    # t048 AC-003: the no-data fallback is a complete applied version, not a
    # half-built object with an empty hash.
    from cbrowser.network_config import (
        compute_caddyfile_sha256,
        derive_origin_whitelist,
        generate_caddyfile,
    )

    fallback = resp.applied_version
    assert len(fallback.caddyfile_sha256) == 64
    assert fallback.caddyfile_sha256 == compute_caddyfile_sha256(
        generate_caddyfile(fallback.config)
    )
    assert fallback.origin_whitelist == derive_origin_whitelist(fallback.config)

    # 2. Save pending changes only pending, applied remains unchanged (AC-001, AC-002)
    new_pending = NetworkAccessConfig(
        lan_access_enabled=True,
        lan_advertised_ip="192.168.31.76",
    )
    await repo.save_pending_network_config(new_pending)

    resp2 = await repo.get_network_access_settings()
    assert resp2.pending_config.lan_access_enabled
    assert resp2.pending_config.lan_advertised_ip == "192.168.31.76"
    assert resp2.applied_version.version == 1
    assert not resp2.applied_version.config.lan_access_enabled


@pytest.mark.asyncio
async def test_network_applied_version_and_operations(session_maker):
    repo = ProfileRepository(session_maker)

    # Apply version 2
    v2 = AppliedNetworkAccessVersion(
        version=2,
        config=NetworkAccessConfig(
            lan_access_enabled=True,
            lan_advertised_ip="192.168.31.76",
        ),
        applied_at="2026-11-08T05:00:00+08:00",
        caddyfile_sha256="a" * 64,
        origin_whitelist=["https://127.0.0.1:56661", "https://192.168.31.76:56661"],
    )
    await repo.record_applied_network_version(v2)

    resp = await repo.get_network_access_settings()
    assert resp.applied_version.version == 2
    assert resp.applied_version.config.lan_access_enabled
    assert resp.applied_version.config.lan_advertised_ip == "192.168.31.76"
    assert resp.applied_version.caddyfile_sha256 == "a" * 64

    # Operation persistence
    op = NetworkApplyOperation(
        operation_id="op-1",
        target_version=2,
        phase=NetworkApplyPhase.REBUILDING_CADDY,
        created_at="2026-11-08T05:00:01+08:00",
        updated_at="2026-11-08T05:00:01+08:00",
    )
    await repo.save_network_operation(op)

    current_op = await repo.get_active_network_operation()
    assert current_op is not None
    assert current_op.operation_id == "op-1"
    assert current_op.phase == NetworkApplyPhase.REBUILDING_CADDY

    # Mark completed
    op.phase = NetworkApplyPhase.COMPLETED
    op.updated_at = "2026-11-08T05:00:05+08:00"
    await repo.save_network_operation(op)

    # Active operation should now be None because it's terminal
    assert await repo.get_active_network_operation() is None
    # But operation can be queried by ID
    fetched = await repo.get_network_operation("op-1")
    assert fetched is not None
    assert fetched.phase == NetworkApplyPhase.COMPLETED
