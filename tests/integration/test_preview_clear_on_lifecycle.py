from __future__ import annotations

from pathlib import Path

import pytest

from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import ProfileConfig
from cbrowser.preview import (
    PreviewMeta,
    PreviewPolicy,
    commit_preview,
    preview_dir,
    write_policy,
)
from cbrowser.services.profile_service import ProfileService


def _seed(directory: Path, captured_at: str) -> None:
    policy = PreviewPolicy(
        enabled=True, epoch=0, runtime_instance_id="inst-1"
    )
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at=captured_at,
        runtime_instance_id="inst-1",
        policy_epoch=0,
    )
    assert commit_preview(directory, b"\xff\xd8jpeg", meta, policy)


@pytest.mark.asyncio
async def test_preview_cleared_on_delete_and_reset(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    run_database_migrations(db_path)
    engine, session_maker = create_engine_and_maker(db_path)
    try:
        repo = ProfileRepository(session_maker)
        service = ProfileService(repo, data_root=tmp_path)

        deleted = await repo.create_profile(
            ProfileConfig(name="Delete Preview"),
            user_data_dir=str(tmp_path / "profiles" / "del" / "profile"),
        )
        deleted_dir = preview_dir(tmp_path, deleted.id)
        _seed(deleted_dir, "t-delete")
        assert (deleted_dir / "latest.jpg").is_file()
        await service.delete_profile(deleted.id)
        assert not (deleted_dir / "latest.jpg").exists()
        assert not (deleted_dir / "meta.json").exists()

        reset = await repo.create_profile(
            ProfileConfig(name="Reset Preview"),
            user_data_dir=str(tmp_path / "profiles" / "rst" / "profile"),
        )
        reset_dir = preview_dir(tmp_path, reset.id)
        _seed(reset_dir, "t-reset")
        assert (reset_dir / "latest.jpg").is_file()
        await service.reset_profile(reset.id)
        assert not (reset_dir / "latest.jpg").exists()
        assert not (reset_dir / "meta.json").exists()
    finally:
        await engine.dispose()
