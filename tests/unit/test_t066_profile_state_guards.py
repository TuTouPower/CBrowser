"""t066: profile state guards — unified seed range, residual-writer
refusal for state-rewriting operations, and config-save state retention."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import (
    FINGERPRINT_SEED_MAX,
    FINGERPRINT_SEED_MIN,
    ProfileConfig,
    derive_fingerprint_seed,
    generate_fingerprint_seed,
)
from cbrowser.services.profile_service import (
    ProfileRunningError,
    ProfileService,
    _manifest,
)


async def _context(tmp_path: Path):
    db = tmp_path / "profiles.db"
    run_database_migrations(db)
    engine, maker = create_engine_and_maker(db)
    repo = ProfileRepository(maker)
    profile_dir = tmp_path / "profiles" / "p1" / "profile"
    profile_dir.mkdir(parents=True)
    source = await repo.create_profile(
        ProfileConfig(name="Source", fingerprint_seed=123456),
        profile_id="p1",
        user_data_dir=str(profile_dir),
    )
    service = ProfileService(repo, runtime_uid=os.getuid(), runtime_gid=os.getgid())
    return engine, repo, service, source, profile_dir


async def _make_proxy(repo: ProfileRepository) -> str:
    proxy = await repo.create_proxy(
        {
            "name": "guard-proxy",
            "scheme": "http",
            "host": "proxy.test",
            "port": 8080,
        }
    )
    return proxy.id


def _write_state(profile_dir: Path) -> None:
    (profile_dir / "Default").mkdir(exist_ok=True)
    (profile_dir / "Default" / "Cookies").write_bytes(b"cookie-data")
    (profile_dir / "Default" / "Preferences").write_text("{}", encoding="utf-8")
    (profile_dir / "Local State").write_text("{}", encoding="utf-8")


def test_seed_space_is_a_single_declared_range() -> None:
    assert (FINGERPRINT_SEED_MIN, FINGERPRINT_SEED_MAX) == (100000, 999999)
    for _ in range(200):
        seed = generate_fingerprint_seed()
        assert FINGERPRINT_SEED_MIN <= seed <= FINGERPRINT_SEED_MAX


def test_operation_seed_derivation_is_deterministic_and_in_range() -> None:
    seen: set[int] = set()
    for _ in range(200):
        operation_id = secrets.token_hex(16)
        first = derive_fingerprint_seed(operation_id)
        assert first == derive_fingerprint_seed(operation_id)
        assert FINGERPRINT_SEED_MIN <= first <= FINGERPRINT_SEED_MAX
        seen.add(first)
    # Distinct operations must not collapse onto a handful of seeds.
    assert len(seen) > 150


@pytest.mark.asyncio
async def test_reset_with_operation_id_uses_unified_seed_range(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir = await _context(tmp_path)
    _write_state(profile_dir)
    try:
        for _ in range(5):
            updated = await service.reset_profile(
                "p1", operation_id=secrets.token_hex(16)
            )
            assert (
                FINGERPRINT_SEED_MIN
                <= updated.config.fingerprint_seed
                <= FINGERPRINT_SEED_MAX
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_residual_runtime_instance_blocks_state_rewrite(
    tmp_path: Path,
) -> None:
    """desired/observed both read stopped, but a runtime instance is still
    bound: that binding is the durable trace of an actual writer, so
    duplicate-with-state and reset must refuse (AC-005)."""
    engine, repo, service, source, profile_dir = await _context(tmp_path)
    _write_state(profile_dir)
    original = service.get_runtime

    async def ghost_runtime(profile_id: str):
        runtime = await original(profile_id)
        return runtime.model_copy(update={"runtime_instance_id": "ghost-1"})

    service.get_runtime = ghost_runtime  # type: ignore[method-assign]
    try:
        with pytest.raises(ProfileRunningError):
            await service.duplicate_profile("p1", include_browser_state=True)
        with pytest.raises(ProfileRunningError):
            await service.reset_profile("p1")
        # Nothing was copied, cleared, or re-seeded.
        assert (profile_dir / "Default" / "Cookies").read_bytes() == b"cookie-data"
        assert sorted(p.name for p in (tmp_path / "profiles").iterdir()) == ["p1"]
        current = await repo.get_profile("p1")
        assert current is not None
        assert current.config.fingerprint_seed == 123456
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_config_save_preserves_browser_state_directory(
    tmp_path: Path,
) -> None:
    """Ordinary config saves — including the proxy and fingerprint
    field classes AC-001 names — never clear or rebuild the browser
    state directory."""
    engine, repo, service, source, profile_dir = await _context(tmp_path)
    _write_state(profile_dir)
    before = _manifest(profile_dir)
    proxy_id = await _make_proxy(repo)
    try:
        updated = await service.update_profile(
            "p1",
            {
                "notes": "changed",
                "proxy_id": proxy_id,
                "screen_width": 1280,
                "screen_height": 900,
                "locale": "en-US",
                "timezone": "America/New_York",
                "gpu_family": "nvidia",
                "humanize": False,
            },
        )
        assert updated.config.notes == "changed"
        assert updated.config.proxy_id == proxy_id
        assert updated.config.gpu_family == "nvidia"
        assert updated.config.screen_width == 1280
        assert updated.config.screen_height == 900
        assert updated.config.locale == "en-US"
        assert updated.config.timezone == "America/New_York"
        assert updated.config.humanize is False
        assert updated.config.fingerprint_seed == 123456
        assert _manifest(profile_dir) == before
        assert (profile_dir / "Default" / "Cookies").read_bytes() == b"cookie-data"
    finally:
        await engine.dispose()
