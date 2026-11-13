"""Profile config/state copy and reset semantics."""

from __future__ import annotations

import asyncio
import os
import secrets
import stat
from pathlib import Path

import pytest
from cbrowser.adapters.database.artifact_repository import ArtifactRepository
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import (
    InvalidProfileNameError,
    ProfileOperationConflictError,
    ProfileRunningError,
    ProfileService,
)


async def _context(tmp_path: Path):
    db = tmp_path / "profiles.db"
    run_database_migrations(db)
    engine, maker = create_engine_and_maker(db)
    repo = ProfileRepository(maker)
    profile_dir = tmp_path / "profiles" / "p1" / "profile"
    profile_dir.mkdir(parents=True)
    group = await repo.create_group("Research", "slate", 0)
    proxy = await repo.create_proxy(
        {
            "name": "source-proxy",
            "scheme": "http",
            "host": "proxy.test",
            "port": 8080,
        }
    )
    source = await repo.create_profile(
        ProfileConfig(
            name="Source",
            fingerprint_seed=12345,
            group_id=group.id,
            proxy_id=proxy.id,
            timezone="Asia/Shanghai",
            locale="zh-CN",
            notes="keep me",
        ),
        profile_id="p1",
        user_data_dir=str(profile_dir),
    )
    service = ProfileService(
        repo, runtime_uid=os.getuid(), runtime_gid=os.getgid()
    )
    return engine, repo, service, source, profile_dir, maker


def _write_state(profile_dir: Path) -> None:
    (profile_dir / "Cookies").write_bytes(b"cookie-data")
    (profile_dir / "Default").mkdir()
    (profile_dir / "Default" / "Preferences").write_text("{}", encoding="utf-8")
    # Local State rides along verbatim in a state copy: the engine has
    # no per-profile OSCrypt key root anchored in it (t066 spike), and
    # the manifest equality assertions below cover its byte identity.
    (profile_dir / "Local State").write_text(
        '{"os_crypt": {}}', encoding="utf-8"
    )
    (profile_dir / "SingletonLock").symlink_to("host-1234")
    (profile_dir / "SingletonCookie").symlink_to("cookie-target")
    (profile_dir / "SingletonSocket").symlink_to("socket-target")


@pytest.mark.asyncio
async def test_config_only_duplicate_preserves_ref_fields_and_skips_state(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    try:
        clone = await service.duplicate_profile("p1")
        assert clone.id != source.id
        assert clone.config.name == "Source (copy)"
        assert clone.config.fingerprint_seed == 12345
        assert clone.config.group_id == source.config.group_id
        assert clone.config.proxy_id == source.config.proxy_id
        assert clone.config.timezone == "Asia/Shanghai"
        assert clone.config.locale == "zh-CN"
        assert clone.config.notes == "keep me"
        assert clone.config == source.config.model_copy(
            update={"name": "Source (copy)"}
        )
        versions = await repo.list_config_versions(clone.id)
        assert versions[0].version == 1
        assert versions[0].config == clone.config.model_dump()
        assert clone.current_config_version == 1
        assert not Path(clone.user_data_dir).exists()
        assert (profile_dir / "Cookies").read_bytes() == b"cookie-data"
        assert await repo.list_config_versions(clone.id)
        assert (
            await ArtifactRepository(maker).list_artifacts(clone.id) == []
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_state_duplicate_copies_files_and_skips_singleton(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    try:
        clone = await service.duplicate_profile("p1", include_browser_state=True)
        clone_dir = Path(clone.user_data_dir)
        assert clone_dir.is_dir()
        assert (clone_dir / "Cookies").read_bytes() == b"cookie-data"
        assert (clone_dir / "Default" / "Preferences").read_text() == "{}"
        assert not (clone_dir / "SingletonLock").exists()
        assert not (clone_dir / "SingletonCookie").exists()
        assert not (clone_dir / "SingletonSocket").exists()
        assert (profile_dir / "SingletonLock").is_symlink()
        assert (profile_dir / "SingletonCookie").is_symlink()
        assert (profile_dir / "SingletonSocket").is_symlink()
        assert (profile_dir / "Cookies").read_bytes() == b"cookie-data"
        from cbrowser.services.profile_service import _manifest

        assert _manifest(clone_dir) == _manifest(profile_dir)
        assert (
            await ArtifactRepository(maker).list_artifacts(clone.id) == []
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_state_duplicate_rejects_running_profile(tmp_path: Path) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    try:
        await repo.set_desired_state("p1", "running")
        with pytest.raises(ProfileRunningError):
            await service.duplicate_profile("p1", include_browser_state=True)
        assert list((tmp_path / "profiles").glob("*/profile")) == [profile_dir]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reset_rerolls_seed_and_preserves_refs_without_touching_other_profiles(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    other_dir = tmp_path / "profiles" / "p2" / "profile"
    other_dir.mkdir(parents=True)
    (other_dir / "Cookies").write_bytes(b"other")
    await repo.create_profile(
        ProfileConfig(name="Other", fingerprint_seed=777),
        profile_id="p2",
        user_data_dir=str(other_dir),
    )
    _write_state(profile_dir)
    artifacts = ArtifactRepository(maker)
    artifact_path = tmp_path / "artifacts" / "p1" / "a1" / "keep.csv"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"keep-me")
    await artifacts.create_artifact(
        profile_id="p1",
        artifact_id="a1",
        name="keep.csv",
        size=7,
        kind="upload",
        state="ready",
        content_type="text/csv",
        sha256="0" * 64,
        storage_path=str(artifact_path),
    )
    try:
        updated = await service.reset_profile("p1")
        assert updated.config.fingerprint_seed != 12345
        assert updated.config.name == "Source"
        assert updated.config.group_id == source.config.group_id
        assert updated.config.proxy_id == source.config.proxy_id
        assert updated.config.notes == "keep me"
        assert updated.current_config_version == 2
        versions = await repo.list_config_versions("p1")
        assert versions[-1].version == 2
        assert (
            versions[-1].config["fingerprint_seed"] == updated.config.fingerprint_seed
        )
        assert list(profile_dir.iterdir()) == []
        assert (other_dir / "Cookies").read_bytes() == b"other"
        assert not list((tmp_path / "profiles" / "p1").glob(".reset-backup-*"))
        # Independent Artifacts survive a reset untouched (AC-004).
        remaining = await artifacts.list_artifacts("p1")
        assert [a.id for a in remaining] == ["a1"]
        assert artifact_path.read_bytes() == b"keep-me"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reset_restores_source_when_database_update_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    original_seed = source.config.fingerprint_seed

    async def fail_update(**kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repo, "update_profile", fail_update)
    try:
        with pytest.raises(RuntimeError, match="database is locked"):
            await service.reset_profile("p1")
        assert (profile_dir / "Cookies").read_bytes() == b"cookie-data"
        restored = await repo.get_profile("p1")
        assert restored is not None
        assert restored.config.fingerprint_seed == original_seed
        assert not list((tmp_path / "profiles" / "p1").glob(".reset-backup-*"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_and_reset_are_idempotent_with_operation_id(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    try:
        operation = secrets.token_hex(16)
        first = await service.duplicate_profile("p1", operation_id=operation)
        second = await service.duplicate_profile("p1", operation_id=operation)
        assert first.id == second.id
        assert len(await repo.list_profiles()) == 2

        reset_operation = secrets.token_hex(16)
        reset_first = await service.reset_profile("p1", operation_id=reset_operation)
        reset_second = await service.reset_profile("p1", operation_id=reset_operation)
        assert (
            reset_first.config.fingerprint_seed == reset_second.config.fingerprint_seed
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_rejects_blank_name_and_caps_long_default_name(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    long_name = "x" * 255
    await repo.update_profile("p1", {"name": long_name})
    try:
        with pytest.raises(InvalidProfileNameError):
            await service.duplicate_profile("p1", name="   ")
        clone = await service.duplicate_profile("p1")
        assert len(clone.config.name) <= 255
        assert clone.id in {profile.id for profile in await repo.list_profiles()}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_state_duplicate_of_unlaunched_profile_creates_empty_clone(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    import shutil

    shutil.rmtree(profile_dir)
    try:
        clone = await service.duplicate_profile("p1", include_browser_state=True)
        assert Path(clone.user_data_dir).is_dir()
        assert list(Path(clone.user_data_dir).iterdir()) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_failure_removes_staged_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)

    async def fail_create(**kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repo, "create_profile", fail_create)
    try:
        with pytest.raises(RuntimeError, match="database is locked"):
            await service.duplicate_profile("p1", include_browser_state=True)
        assert list((tmp_path / "profiles").iterdir()) == [tmp_path / "profiles" / "p1"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_copy_permissions_are_exact_and_private(tmp_path: Path) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    try:
        clone = await service.duplicate_profile("p1", include_browser_state=True)
        clone_dir = Path(clone.user_data_dir)
        assert stat.S_IMODE(clone_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE((clone_dir / "Cookies").stat().st_mode) == 0o600
        assert stat.S_IMODE((clone_dir / "Default").stat().st_mode) == 0o700
        assert (
            stat.S_IMODE((clone_dir / "Default" / "Preferences").stat().st_mode)
            == 0o600
        )
        for path in clone_dir.rglob("*"):
            if not path.is_symlink():
                assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_copy_ownership_failure_raises_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    service.runtime_uid = os.getuid() + 1
    service.runtime_gid = os.getgid() + 1
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    def deny(_path, _uid, _gid, **_kwargs):
        raise PermissionError("not root")

    monkeypatch.setattr(os, "chown", deny)
    try:
        with pytest.raises(PermissionError):
            await service.duplicate_profile("p1", include_browser_state=True)
        assert list((tmp_path / "profiles").iterdir()) == [tmp_path / "profiles" / "p1"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_operation_key_cannot_cross_actions_or_profiles(tmp_path: Path) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    try:
        operation = secrets.token_hex(16)
        await repo.update_profile("p1", {"notes": "changed"}, operation_id=operation)
        with pytest.raises(ProfileOperationConflictError):
            await service.duplicate_profile("p1", operation_id=operation)
        with pytest.raises(ProfileOperationConflictError):
            await service.reset_profile("p1", operation_id=operation)

        create_op = secrets.token_hex(16)
        await repo.create_profile(ProfileConfig(name="Generic"), operation_id=create_op)
        with pytest.raises(ProfileOperationConflictError):
            await service.duplicate_profile("p1", operation_id=create_op)

        duplicate_op = secrets.token_hex(16)
        await service.duplicate_profile("p1", operation_id=duplicate_op)
        with pytest.raises(ProfileOperationConflictError):
            await service.reset_profile("p1", operation_id=duplicate_op)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_reset_with_same_operation_is_idempotent(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    operation = secrets.token_hex(16)
    try:
        first, second = await asyncio.gather(
            service.reset_profile("p1", operation_id=operation),
            service.reset_profile("p1", operation_id=operation),
        )
        assert first.config.fingerprint_seed == second.config.fingerprint_seed
        assert len(await repo.list_profiles()) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_copy_and_reset_reject_starting_or_stopping_source(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    try:
        await repo.bind_runtime_instance("p1", "i1")
        await repo.report_observed_state("p1", "i1", "stopping")
        with pytest.raises(ProfileRunningError):
            await service.duplicate_profile("p1", include_browser_state=True)
        with pytest.raises(ProfileRunningError):
            await service.reset_profile("p1")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_does_not_copy_artifacts(tmp_path: Path) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    artifacts = ArtifactRepository(maker)
    artifact_path = tmp_path / "artifacts" / "p1" / "a1" / "secret.csv"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"secret")
    await artifacts.create_artifact(
        profile_id="p1",
        artifact_id="a1",
        name="secret.csv",
        size=6,
        kind="upload",
        state="ready",
        content_type="text/csv",
        sha256="0" * 64,
        storage_path=str(artifact_path),
    )
    _write_state(profile_dir)
    try:
        config_clone = await service.duplicate_profile("p1")
        state_clone = await service.duplicate_profile("p1", include_browser_state=True)
        assert await artifacts.list_artifacts(config_clone.id) == []
        assert await artifacts.list_artifacts(state_clone.id) == []
        assert len(await artifacts.list_artifacts("p1")) == 1
        assert artifact_path.read_bytes() == b"secret"
        assert not (tmp_path / "artifacts" / state_clone.id).exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_copy_manifest_mismatch_removes_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    import cbrowser.services.profile_service as module

    original = module._copy_user_data

    def corrupt_copy(source_path, target_path, **kwargs):
        original(source_path, target_path, **kwargs)
        (target_path / "extra.txt").write_text("mismatch", encoding="utf-8")

    monkeypatch.setattr(module, "_copy_user_data", corrupt_copy)
    try:
        with pytest.raises(Exception, match="does not match"):
            await service.duplicate_profile("p1", include_browser_state=True)
        assert list((tmp_path / "profiles").iterdir()) == [tmp_path / "profiles" / "p1"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_copy_failure_removes_partial_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    import cbrowser.services.profile_service as module

    def fail_copy(source_path, target_path, **kwargs):
        target_path.mkdir(parents=True, exist_ok=True)
        (target_path / "Cookies").write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(module, "_copy_user_data", fail_copy)
    try:
        with pytest.raises(OSError, match="disk full"):
            await service.duplicate_profile("p1", include_browser_state=True)
        assert list((tmp_path / "profiles").iterdir()) == [tmp_path / "profiles" / "p1"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_running_after_copy_is_rejected_and_clone_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    original = service.get_runtime
    calls = {"count": 0}

    async def runtime_side_effect(profile_id):
        calls["count"] += 1
        if calls["count"] == 1:
            return await original(profile_id)
        return (await original(profile_id)).model_copy(
            update={"desired_state": "running", "observed_state": "running"}
        )

    monkeypatch.setattr(service, "get_runtime", runtime_side_effect)
    try:
        with pytest.raises(ProfileRunningError):
            await service.duplicate_profile("p1", include_browser_state=True)
        assert list((tmp_path / "profiles").iterdir()) == [tmp_path / "profiles" / "p1"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_state_duplicate_same_key_has_no_orphan(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    operation = secrets.token_hex(16)
    try:
        first, second = await asyncio.gather(
            service.duplicate_profile(
                "p1", include_browser_state=True, operation_id=operation
            ),
            service.duplicate_profile(
                "p1", include_browser_state=True, operation_id=operation
            ),
        )
        assert first.id == second.id
        assert sorted(path.name for path in (tmp_path / "profiles").iterdir()) == [
            first.id,
            "p1",
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_key_different_duplicate_payload_conflicts(tmp_path: Path) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    operation = secrets.token_hex(16)
    try:
        await service.duplicate_profile("p1", operation_id=operation)
        with pytest.raises(ProfileOperationConflictError):
            await service.duplicate_profile(
                "p1", include_browser_state=True, operation_id=operation
            )
        with pytest.raises(ProfileOperationConflictError):
            await service.duplicate_profile(
                "p1", name="Different", operation_id=operation
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_copy_ownership_does_not_follow_directory_symlinks(
    tmp_path: Path,
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    victim = tmp_path / "victim"
    victim.mkdir()
    victim.chmod(0o755)
    (profile_dir / "escape").symlink_to(victim)
    try:
        clone = await service.duplicate_profile("p1", include_browser_state=True)
        clone_dir = Path(clone.user_data_dir)
        assert (clone_dir / "escape").is_symlink()
        assert victim.stat().st_mode & 0o777 == 0o755
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_profile_locks_are_released_after_operations(tmp_path: Path) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    try:
        await service.set_desired_state("p1", "stopped")
        assert service.locks_idle
        await service.duplicate_profile("p1", include_browser_state=True)
        assert service.locks_idle
        await service.delete_profile("p1")
        assert service.locks_idle
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_copy_ownership_targets_runtime_uid_1000_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, repo, service, source, profile_dir, maker = await _context(tmp_path)
    _write_state(profile_dir)
    calls: list[tuple[Path, int, int]] = []

    def record(target, uid, gid, **_kwargs):
        calls.append((Path(target), uid, gid))

    monkeypatch.setattr(os, "chown", record)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    try:
        await ProfileService(repo, runtime_uid=1000, runtime_gid=1000).duplicate_profile(
            "p1", include_browser_state=True
        )
        assert calls
        assert all((uid, gid) == (1000, 1000) for _, uid, gid in calls)
    finally:
        await engine.dispose()
