"""AC-002 (A4): ordinary profile reads load only the data they return.

Config version history and artifact history must not be read by ordinary
profile queries no matter how large they grow; existence checks are scalar
and download dedupe filters by storage_path inside SQL.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cbrowser.adapters.database.artifact_repository import ArtifactRepository
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import ProfileConfig
from sqlalchemy import event


@pytest.fixture
async def repos(tmp_path: Path):
    db = tmp_path / "loading.db"
    run_database_migrations(db)
    engine, maker = create_engine_and_maker(db)
    yield engine, ProfileRepository(maker), ArtifactRepository(maker)
    await engine.dispose()


def _capture(engine) -> list[str]:
    statements: list[str] = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    return statements


@pytest.mark.asyncio
async def test_ordinary_profile_reads_do_not_load_history_with_refs(repos) -> None:
    engine, profiles, artifacts = repos
    profile = await profiles.create_profile(
        ProfileConfig(name="History", fingerprint_seed=7)
    )
    # Grow immutable history with runtime-config field changes (t035 AC-006:
    # metadata-only edits no longer create a version) and artifact rows.
    for index in range(3):
        await profiles.update_profile(
            profile.id, {"screen_width": 1280 + index}
        )
    for index in range(3):
        await artifacts.create_artifact(
            profile_id=profile.id,
            name=f"file-{index}.csv",
            size=1,
            kind="download",
            state="ready",
            content_type="text/csv",
            sha256=f"{index:064x}",
            storage_path=f"/data/artifacts/{profile.id}/downloads/{index}",
        )

    statements = _capture(engine)
    fetched = await profiles.get_profile(profile.id)
    listed = await profiles.list_profiles()
    joined = "\n".join(statements)
    assert "profile_config_versions" not in joined
    assert "artifacts" not in joined
    assert "FROM profiles" in joined

    # Returned DTOs are unchanged by the loading strategy.
    assert fetched is not None
    assert fetched.config.name == "History"
    assert fetched.current_config_version == 4
    assert [item.id for item in listed] == [profile.id]

    # AC-006: a metadata-only edit (name) must not create a new version.
    await profiles.update_profile(profile.id, {"name": "History renamed"})
    assert (await profiles.get_profile(profile.id)).current_config_version == 4


@pytest.mark.asyncio
async def test_profile_exists_is_scalar(repos) -> None:
    engine, profiles, artifacts = repos
    profile = await profiles.create_profile(
        ProfileConfig(name="Exists", fingerprint_seed=1)
    )
    statements = _capture(engine)
    assert await artifacts.profile_exists(profile.id) is True
    assert await artifacts.profile_exists("missing-profile") is False
    joined = "\n".join(statements)
    assert "profile_config_versions" not in joined
    assert "artifacts" not in joined


@pytest.mark.asyncio
async def test_download_duplicate_filters_path_in_sql(repos) -> None:
    engine, profiles, artifacts = repos
    profile = await profiles.create_profile(
        ProfileConfig(name="Dedupe", fingerprint_seed=1)
    )
    digest = "a" * 64
    created = await artifacts.create_artifact(
        profile_id=profile.id,
        name="report.csv",
        size=3,
        kind="download",
        state="ready",
        content_type="text/csv",
        sha256=digest,
        storage_path="/data/artifacts/p/downloads/one/report.csv",
    )
    statements = _capture(engine)
    found = await artifacts.find_download_duplicate(
        profile.id,
        sha256=digest,
        storage_path="/data/artifacts/p/downloads/one/report.csv",
    )
    assert found is not None and found.id == created.id
    select_statements = [s for s in statements if "storage_path" in s]
    assert select_statements, statements

    missing = await artifacts.find_download_duplicate(
        profile.id,
        sha256=digest,
        storage_path="/data/artifacts/p/downloads/two/report.csv",
    )
    assert missing is None
