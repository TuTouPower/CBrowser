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
    policy = PreviewPolicy(enabled=True, epoch=0, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at=captured_at,
        runtime_instance_id="inst-1",
        policy_epoch=0,
    )
    assert commit_preview(directory, b"\xff\xd8jpeg", meta, policy)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["delete", "reset"])
async def test_lifecycle_removes_every_immutable_preview_frame(tmp_path: Path, action):
    db_path = tmp_path / "test.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    try:
        repo = ProfileRepository(maker)
        service = ProfileService(repo, data_root=tmp_path)
        profile = await repo.create_profile(
            ProfileConfig(name=action),
            user_data_dir=str(tmp_path / "profiles" / action / "profile"),
        )
        directory = preview_dir(tmp_path, profile.id)
        for index in range(2):
            _seed(directory, f"{action}-{index}")
        frames = list(directory.glob("frame_*.jpg"))
        assert len(frames) == 2
        assert (directory / "meta.json").is_file()
        await getattr(service, f"{action}_profile")(profile.id)
        assert all(not p.exists() for p in frames)
        assert list(directory.glob("*.jpg")) == []
        assert not (directory / "meta.json").exists()
    finally:
        await engine.dispose()
