"""t035 profile domain rebuild: Group/Proxy library, config-version split,
runtime lifecycle, and snapshot secrecy (AC-003/004/005/006/009/011).

Every test drives the real ``ProfileRepository`` over a migrated SQLite DB
(``db_context`` fixture in ``tests/unit/conftest.py``).
"""

from __future__ import annotations

import json

import pytest
from cbrowser.adapters.database.models import ProfileConfigVersionModel
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import ProfileRunningError, ProfileService
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def _proxy_payload(name: str = "px", password: str | None = "s3cr3t") -> dict:
    return {
        "name": name,
        "scheme": "socks5",
        "host": "proxy.example.com",
        "port": 1080,
        "username": "user",
        "password": password,
        "region_label": "East",
        "notes": "primary",
    }


# ---- AC-003: Group library -------------------------------------------------


@pytest.mark.asyncio
async def test_group_crud_name_uniqueness_and_reorder(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    g1 = await repo.create_group("Work", "slate", 0)
    g2 = await repo.create_group("Personal", "blue", 1)
    assert [g.id for g in await repo.list_groups()] == [g1.id, g2.id]

    with pytest.raises(ValueError):
        await repo.create_group("Work", "red", 0)

    updated = await repo.update_group(g1.id, {"name": "Office", "color": "teal"})
    assert updated is not None
    assert updated.name == "Office" and updated.color == "teal"

    reordered = await repo.reorder_groups([g2.id, g1.id])
    assert [g.id for g in reordered] == [g2.id, g1.id]

    assert await repo.delete_group(g2.id) is True
    assert await repo.delete_group(g2.id) is False
    assert [g.id for g in await repo.list_groups()] == [g1.id]


@pytest.mark.asyncio
async def test_group_delete_sets_profile_group_id_null(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    group = await repo.create_group("Team", "slate", 0)
    profile = await repo.create_profile(
        ProfileConfig(name="Grouped", group_id=group.id)
    )
    assert profile.config.group_id == group.id

    assert await repo.delete_group(group.id) is True
    fetched = await repo.get_profile(profile.id)
    assert fetched is not None
    assert fetched.config.group_id is None


@pytest.mark.asyncio
async def test_patch_unknown_group_id_is_rejected_by_fk(db_context):
    """The repository writes group_id verbatim; only the FK rejects a dangling
    reference (no explicit existence check).  See the handoff note."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    profile = await repo.create_profile(ProfileConfig(name="Ref Guard"))
    with pytest.raises(IntegrityError):
        await repo.update_profile(profile.id, {"group_id": "missing-group"})


# ---- AC-004: Proxy library + password tri-state ---------------------------


@pytest.mark.asyncio
async def test_proxy_crud_and_response_hides_password(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    created = await repo.create_proxy(_proxy_payload())
    assert created.has_password is True
    assert "password" not in created.model_dump()

    fetched = await repo.get_proxy(created.id)
    assert fetched is not None
    assert fetched.has_password is True
    assert "password" not in fetched.model_dump()

    listed = await repo.list_proxies()
    assert len(listed) == 1
    assert "password" not in listed[0].model_dump()

    with pytest.raises(ValueError):
        await repo.create_proxy(_proxy_payload(name="px"))

    missing, affected = await repo.update_proxy("missing", {"name": "x"}, False)
    assert missing is None and affected == []


@pytest.mark.asyncio
async def test_proxy_password_patch_tristate(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    px = await repo.create_proxy(_proxy_payload())
    revision = px.credential_revision

    # omitted: unchanged
    renamed, affected = await repo.update_proxy(px.id, {"name": "renamed"}, False)
    assert renamed is not None and renamed.name == "renamed"
    assert renamed.has_password is True
    assert renamed.credential_revision == revision
    assert affected == []

    # explicit null: clear
    cleared, _ = await repo.update_proxy(px.id, {"password": None}, True)
    assert cleared is not None and cleared.has_password is False
    assert cleared.credential_revision == revision + 1

    # string: set
    reset, _ = await repo.update_proxy(px.id, {"password": "new-secret"}, True)
    assert reset is not None and reset.has_password is True
    assert reset.credential_revision == revision + 2
    assert "password" not in reset.model_dump()


# ---- AC-005: referenced proxy is refused -----------------------------------


@pytest.mark.asyncio
async def test_delete_proxy_refused_when_referenced(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    px = await repo.create_proxy(_proxy_payload())
    profile = await repo.create_profile(
        ProfileConfig(name="Uses Proxy", proxy_id=px.id)
    )

    assert await repo.delete_proxy(px.id) == (False, 1)
    assert (await repo.get_proxy(px.id)) is not None

    assert await repo.delete_profile(profile.id) is True
    assert await repo.delete_proxy(px.id) == (True, 0)


# ---- AC-006: config-version split + snapshot secrecy ----------------------


@pytest.mark.asyncio
async def test_metadata_and_instant_fields_do_not_create_config_version(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    group = await repo.create_group("Meta", "slate", 0)
    profile = await repo.create_profile(ProfileConfig(name="Meta Profile"))

    updated = await repo.update_profile(
        profile.id,
        {
            "name": "Renamed",
            "notes": "note",
            "sort_order": 3,
            "group_id": group.id,
            "capture_preview": False,
        },
    )
    assert updated is not None
    assert updated.current_config_version == 1
    assert updated.config.name == "Renamed"
    assert updated.config.group_id == group.id
    assert updated.config.capture_preview is False
    assert len(await repo.list_config_versions(profile.id)) == 1


@pytest.mark.asyncio
async def test_runtime_config_field_creates_version_and_snapshot_has_no_password(
    db_context,
):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    px = await repo.create_proxy(_proxy_payload())
    profile = await repo.create_profile(
        ProfileConfig(name="Versioned", proxy_id=px.id)
    )

    updated = await repo.update_profile(profile.id, {"screen_width": 1280})
    assert updated is not None
    assert updated.current_config_version == 2
    versions = await repo.list_config_versions(profile.id)
    assert [v.version for v in versions] == [1, 2]

    async with session_maker() as session:
        rows = (
            await session.execute(
                select(ProfileConfigVersionModel).where(
                    ProfileConfigVersionModel.profile_id == profile.id
                )
            )
        ).scalars().all()
        payloads = [json.loads(row.snapshot) for row in rows]
    for payload in payloads:
        assert "password" not in payload
        assert "password" not in payload["config"]
    assert payloads[-1]["proxy_credential_revision"] == px.credential_revision


@pytest.mark.asyncio
async def test_proxy_connection_change_regenerates_versions_for_referencing_profiles(
    db_context,
):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    px = await repo.create_proxy(_proxy_payload())
    profile = await repo.create_profile(
        ProfileConfig(name="Bound To Proxy", proxy_id=px.id)
    )

    # Presentation metadata never regenerates versions.
    _, affected = await repo.update_proxy(
        px.id, {"name": "renamed", "notes": "new note", "region_label": "West"}, False
    )
    assert affected == []
    assert (await repo.get_profile(profile.id)).current_config_version == 1

    # A connection field regenerates a version for every referencing profile.
    _, affected = await repo.update_proxy(px.id, {"host": "new.example.com"}, False)
    assert affected == [profile.id]
    assert (await repo.get_profile(profile.id)).current_config_version == 2
    assert len(await repo.list_config_versions(profile.id)) == 2

    # A password rotation bumps the credential revision and regenerates too.
    _, affected = await repo.update_proxy(px.id, {"password": "rotated"}, True)
    assert affected == [profile.id]
    assert (await repo.get_proxy(px.id)).credential_revision == 2
    assert (await repo.get_profile(profile.id)).current_config_version == 3


# ---- AC-009: runtime timestamps / browser version -------------------------


@pytest.mark.asyncio
async def test_observed_running_and_terminal_write_timestamps(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    profile = await repo.create_profile(ProfileConfig(name="Lifecycle"))
    await repo.bind_runtime_instance(profile.id, "inst_1", config_version=1)

    running = await repo.report_observed_state(
        profile.id,
        "inst_1",
        "running",
        browser_product="Chrome/146.0.0.0",
        browser_user_agent="Mozilla/5.0",
    )
    assert running is not None
    assert running.last_started_at is not None
    assert running.browser_product == "Chrome/146.0.0.0"
    assert running.browser_user_agent == "Mozilla/5.0"

    stopped = await repo.report_observed_state(profile.id, "inst_1", "stopped")
    assert stopped is not None
    assert stopped.last_stopped_at is not None
    assert stopped.browser_product is None
    assert stopped.browser_user_agent is None


# ---- AC-011: running delete refused; error without instance deletable ------


@pytest.mark.asyncio
async def test_delete_running_profile_raises_but_error_without_instance_can_delete(
    db_context,
):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    service = ProfileService(repo)

    running_profile = await repo.create_profile(ProfileConfig(name="Running"))
    await repo.set_desired_state(running_profile.id, "running")
    with pytest.raises(ProfileRunningError):
        await service.delete_profile(running_profile.id)
    assert (await repo.get_profile(running_profile.id)) is not None

    error_profile = await repo.create_profile(ProfileConfig(name="Errored"))
    await repo.bind_runtime_instance(error_profile.id, "inst_err", config_version=1)
    await repo.report_observed_state(
        error_profile.id, "inst_err", "error", reason="process_lost"
    )
    runtime = await repo.get_runtime(error_profile.id)
    assert runtime.observed_state == "error"
    assert runtime.runtime_instance_id is None
    assert await service.delete_profile(error_profile.id) is True
    assert (await repo.get_profile(error_profile.id)) is None


@pytest.mark.asyncio
async def test_config_version_snapshot_exposes_proxy_credential_revision(
    db_context,
):
    """AC-004: every version snapshot carries the proxy credential revision
    (never the password), and the version API exposes it on the DTO.  A
    profile without a proxy has no credential revision."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    px = await repo.create_proxy(_proxy_payload())
    profile = await repo.create_profile(
        ProfileConfig(name="Revisioned", proxy_id=px.id)
    )

    v1 = await repo.get_config_version(profile.id, 1)
    assert v1 is not None
    assert v1.proxy_credential_revision == px.credential_revision

    await repo.update_profile(profile.id, {"screen_width": 1280})
    v2 = await repo.get_config_version(profile.id, 2)
    assert v2 is not None
    assert v2.proxy_credential_revision == px.credential_revision

    plain = await repo.create_profile(ProfileConfig(name="No proxy"))
    v1_plain = await repo.get_config_version(plain.id, 1)
    assert v1_plain is not None
    assert v1_plain.proxy_credential_revision is None


def test_group_and_proxy_request_validation_rejects_invalid_values() -> None:
    """AC-003/004: group name/color and proxy link are validated at the
    request boundary before reaching the repository.

    t052: the proxy entry is link-only, so the old flat scheme/host/port
    cases are replaced by link-validation cases with the same intent
    (invalid values are rejected before the repository is touched).
    """
    from pydantic import ValidationError

    from cbrowser.domain.models import GroupCreateRequest, ProxyCreateRequest

    with pytest.raises(ValidationError):
        GroupCreateRequest(name="x" * 65)
    with pytest.raises(ValidationError):
        GroupCreateRequest(name="g", color="neon")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ProxyCreateRequest(proxy_url="ftp://proxy.example.com:8080")
    with pytest.raises(ValidationError):
        ProxyCreateRequest(proxy_url="http://proxy.example.com:0")
    with pytest.raises(ValidationError):
        ProxyCreateRequest(proxy_url="")
    with pytest.raises(ValidationError):
        # Flat fields are no longer a valid entry shape (t052 link-only).
        ProxyCreateRequest(proxy_url="http://h:8080", scheme="http")  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_delete_profile_removes_private_directories(
    db_context, tmp_path
) -> None:
    """AC-011: after deleting a stopped profile, its DB row and every
    profile-private directory are gone."""
    from pathlib import Path

    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    service = ProfileService(repo, data_root=Path(tmp_path))
    profile = await repo.create_profile(ProfileConfig(name="To delete"))
    for sub in ("profiles", "runtime", "runtime-events"):
        directory = tmp_path / sub / profile.id
        directory.mkdir(parents=True)
        (directory / "marker").write_text("x", encoding="utf-8")

    assert await service.delete_profile(profile.id) is True
    assert await repo.get_profile(profile.id) is None
    for sub in ("profiles", "runtime", "runtime-events"):
        assert not (tmp_path / sub / profile.id).exists()


@pytest.mark.asyncio
async def test_delete_profile_logs_directory_cleanup_failure(
    db_context, tmp_path, monkeypatch, caplog
) -> None:
    """AC-011: a failed private-directory cleanup is observable, not
    silently swallowed."""
    from pathlib import Path

    from cbrowser.services import profile_service as ps

    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    service = ProfileService(repo, data_root=Path(tmp_path))
    profile = await repo.create_profile(ProfileConfig(name="Cleanup failure"))
    (tmp_path / "profiles" / profile.id).mkdir(parents=True)

    def fail(_path):
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(ps.shutil, "rmtree", fail)
    with caplog.at_level("WARNING", logger="cbrowser.services.profile_service"):
        assert await service.delete_profile(profile.id) is True
    assert "Profile directory cleanup failed" in caplog.text
