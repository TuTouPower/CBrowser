"""Artifact storage/service behavior: atomicity, quota, MIME and reconciliation."""

from __future__ import annotations

import asyncio
import os
import secrets
import stat
from pathlib import Path

import pytest
from cbrowser.adapters.database.artifact_repository import ArtifactRepository
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.models import ArtifactModel, RuntimeEventModel
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import (
    create_engine_and_maker,
    write_transaction,
)
from cbrowser.adapters.filesystem.artifact_store import (
    ArtifactError,
    ArtifactInsufficientStorage,
    ArtifactInvalidContentType,
    ArtifactInvalidName,
    ArtifactNotFound,
    ArtifactQuotaExceeded,
    ArtifactStore,
    ArtifactTooLarge,
    safe_filename,
)
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.artifact_service import ArtifactService


def _chunks(payload: bytes):
    async def run():
        for index in range(0, len(payload), 3):
            yield payload[index : index + 3]

    return run()


async def _context(tmp_path: Path):
    db = tmp_path / "artifacts.db"
    run_database_migrations(db)
    engine, maker = create_engine_and_maker(db)
    repo = ProfileRepository(maker)
    profile = await repo.create_profile(
        ProfileConfig(name="Artifacts", fingerprint_seed=1)
    )
    # Instance "i1" is the profile's bound runtime instance, so download
    # ingests in these tests pass the A40 instance-trust check.
    await repo.bind_runtime_instance(profile.id, "i1")
    store = ArtifactStore(
        tmp_path / "artifact-root",
        runtime_uid=os.getuid(),
        runtime_gid=os.getgid(),
    )
    service = ArtifactService(
        ArtifactRepository(maker),
        store,
        max_artifact_bytes=64,
        max_artifacts_per_profile=2,
        max_profile_bytes=128,
    )
    return engine, store, service, profile.id


def test_safe_filename_neutralises_traversal_and_temporary_names() -> None:
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("..\\..\\windows\\cfg") == "cfg"
    assert safe_filename("") == "file"
    assert safe_filename("with\x00null.csv") == "withnull.csv"


@pytest.mark.asyncio
async def test_upload_publishes_atomically_and_returns_container_path(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        artifact = await service.upload(
            profile_id,
            "../../report.csv",
            "text/csv",
            _chunks(b"a,b\n1,2\n"),
        )
        assert artifact.name == "report.csv"
        assert artifact.size == 8
        assert artifact.sha256
        path = Path(artifact.storage_path)
        assert path.is_file()
        assert path.read_bytes() == b"a,b\n1,2\n"
        assert store.uploads_dir(profile_id) in path.parents
        assert service.container_path(artifact) == (
            f"/exchange/uploads/{artifact.id}/report.csv"
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_oversize_upload_leaves_no_half_file(tmp_path: Path) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        with pytest.raises(ArtifactTooLarge):
            await service.upload(profile_id, "big.csv", "text/csv", _chunks(b"x" * 65))
        assert [
            item for item in store.profile_dir(profile_id).rglob("*") if item.is_file()
        ] == []
        assert await service.list(profile_id) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quota_is_enforced(tmp_path: Path) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        await service.upload(profile_id, "one.csv", "text/csv", _chunks(b"1"))
        await service.upload(profile_id, "two.csv", "text/csv", _chunks(b"2"))
        with pytest.raises(ArtifactQuotaExceeded):
            await service.upload(profile_id, "three.csv", "text/csv", _chunks(b"3"))
    finally:
        await engine.dispose()


# Policy change (A54, user decision D2=A): the previous
# test_quota_and_mime_are_enforced asserted uploads with an executable
# MIME type are rejected. File exchange now allows arbitrary content;
# the tests below pin the new policy instead of the removed one.


@pytest.mark.asyncio
async def test_executable_upload_is_accepted_with_declared_type(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        artifact = await service.upload(
            profile_id, "bad.sh", "application/x-sh", _chunks(b"rm -rf /")
        )
        assert artifact.content_type == "application/x-sh"
        assert artifact.state == "ready"
    finally:
        await engine.dispose()


def test_validate_content_type_unified_rules() -> None:
    from cbrowser.adapters.filesystem.artifact_store import validate_content_type

    # Missing type defaults; parameters drop; case normalizes.
    assert validate_content_type(None) == "application/octet-stream"
    assert validate_content_type("Text/CSV; charset=utf-8") == "text/csv"
    # Executable types are ordinary metadata now.
    assert validate_content_type("application/x-msdownload") == (
        "application/x-msdownload"
    )
    assert validate_content_type("application/x-sh") == "application/x-sh"
    # Empty is treated as missing, like None.
    assert validate_content_type("") == "application/octet-stream"
    # Illegal header values are still rejected on both entry points.
    for illegal in (
        "text/csv\r\nX-Injected: 1",
        "not a mime type",
        "text/",
        "/csv",
        "text/csv/extra",
    ):
        with pytest.raises(ArtifactInvalidContentType):
            validate_content_type(illegal)


@pytest.mark.asyncio
async def test_insufficient_disk_space_refuses_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        reserve = 16 * 1024 * 1024
        monkeypatch.setattr(store, "free_bytes", lambda: reserve + 10)
        with pytest.raises(ArtifactInsufficientStorage):
            await service.upload(
                profile_id,
                "one.csv",
                "text/csv",
                _chunks(b"x" * 20),
                size_hint=20,
            )
        assert await service.list(profile_id) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_download_ingest_deduplicates_and_skips_partial_files(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        payload = b"store_id,orders\n1,2\n"
        source = downloads / "guid-1"
        source.write_bytes(payload)
        partial = downloads / "guid-2.crdownload"
        partial.write_bytes(b"partial")

        first = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(source),
            name="orders.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert first is not None and first.created is True
        canonical = Path(first.artifact.storage_path)
        assert canonical.read_bytes() == payload
        assert not source.exists()

        second = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(canonical),
            name="orders.csv",
            sha256=first.artifact.sha256,
            size=len(payload),
            content_type=None,
        )
        assert second is not None and second.created is False
        assert second.artifact.id == first.artifact.id
        assert await service.list(profile_id) == [first.artifact]

        assert partial.exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_profile_byte_quota_is_enforced_after_streaming(tmp_path: Path) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    service.max_profile_bytes = 10
    try:
        await service.upload(profile_id, "first.csv", "text/csv", _chunks(b"12345678"))
        with pytest.raises(ArtifactQuotaExceeded):
            await service.upload(
                profile_id, "second.csv", "text/csv", _chunks(b"12345678")
            )
        stored = [
            item.name
            for item in store.profile_dir(profile_id).rglob("*")
            if item.is_file()
        ]
        assert stored == ["first.csv"]
        assert [item.name for item in await service.list(profile_id)] == ["first.csv"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_checksum_with_different_name_is_a_distinct_artifact(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        payload = b"same-payload"
        first_source = downloads / "first"
        second_source = downloads / "second"
        first_source.write_bytes(payload)
        second_source.write_bytes(payload)
        first = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(first_source),
            name="first.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        second = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(second_source),
            name="second.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert first is not None and first.created is True
        assert second is not None and second.created is True
        assert first.artifact.sha256 == second.artifact.sha256
        assert {item.name for item in await service.list(profile_id)} == {
            "first.csv",
            "second.csv",
        }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_name_with_different_download_path_is_distinct(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        payload = b"same-name-payload"
        first_source = downloads / "guid-1"
        second_source = downloads / "guid-2"
        first_source.write_bytes(payload)
        second_source.write_bytes(payload)
        first = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(first_source),
            name="report.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        second = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(second_source),
            name="report.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert first is not None and first.created is True
        assert second is not None and second.created is True
        assert first.artifact.id != second.artifact.id
        assert len(await service.list(profile_id)) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_executable_download_keeps_its_declared_type(
    tmp_path: Path,
) -> None:
    """A54: downloads are no longer force re-marked as octet-stream.

    Replaces test_executable_download_is_registered_as_octet_stream, which
    pinned the removed download-side re-marking branch.
    """
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        source = downloads / "guid"
        source.write_bytes(b"MZ")
        created = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(source),
            name="installer.exe",
            sha256=None,
            size=None,
            content_type="application/x-msdownload",
        )
        assert created is not None and created.created is True
        assert created.artifact.content_type == "application/x-msdownload"
        assert created.artifact.name == "installer.exe"

        script = downloads / "guid-2"
        script.write_bytes(b"#!/bin/sh\n")
        created_script = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(script),
            name="run.sh",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert created_script is not None and created_script.created is True
        # The type guessed from the filename is kept as metadata instead of
        # being re-marked to application/octet-stream.
        import mimetypes

        guessed = mimetypes.guess_type("run.sh")[0]
        assert guessed is not None and guessed != "application/octet-stream"
        assert created_script.artifact.content_type == guessed
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_db_failure_restores_downloaded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        source = downloads / "guid"
        payload = b"must-not-be-lost"
        source.write_bytes(payload)

        async def fail_create(**kwargs):
            raise RuntimeError("database is locked")

        monkeypatch.setattr(service.repository, "create_artifact", fail_create)
        with pytest.raises(RuntimeError, match="database is locked"):
            await service.ingest_download(
                profile_id,
                runtime_instance_id="i1",
                path=str(source),
                name="report.csv",
                sha256=None,
                size=None,
                content_type=None,
            )
        assert source.is_file()
        assert source.read_bytes() == payload
        assert await service.list(profile_id) == []
    finally:
        await engine.dispose()


def test_uploaded_file_has_exact_runtime_permissions(tmp_path: Path) -> None:
    async def run():
        engine, store, service, profile_id = await _context(tmp_path)
        try:
            artifact = await service.upload(
                profile_id, "readable.csv", "text/csv", _chunks(b"hello")
            )
            path = Path(artifact.storage_path)
            assert stat.S_IMODE(path.stat().st_mode) == 0o640
            assert stat.S_IMODE(path.parent.stat().st_mode) == 0o750
            assert stat.S_IMODE(store.uploads_dir(profile_id).stat().st_mode) == 0o750
            assert path.stat().st_uid == os.getuid()
            assert path.stat().st_gid == os.getgid()
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_artifact_ownership_targets_runtime_uid_1000_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ArtifactStore(
        tmp_path / "artifact-root", runtime_uid=1000, runtime_gid=1000
    )
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"payload")
    calls: list[tuple[Path, int, int]] = []

    def record(target, uid, gid, **_kwargs):
        calls.append((Path(target), uid, gid))

    monkeypatch.setattr(os, "chown", record)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    store._apply_runtime_permissions(path, directory=False)

    assert calls == [(path, 1000, 1000)]
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_artifact_ownership_failure_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run():
        engine, store, service, profile_id = await _context(tmp_path)
        store.runtime_uid = os.getuid() + 1
        store.runtime_gid = os.getgid() + 1
        monkeypatch.setattr(os, "geteuid", lambda: 0)

        def deny(_path, _uid, _gid, **_kwargs):
            raise PermissionError("not root")

        monkeypatch.setattr(os, "chown", deny)
        try:
            with pytest.raises(ArtifactError, match="Cannot assign artifact ownership"):
                await service.upload(
                    profile_id, "denied.csv", "text/csv", _chunks(b"hello")
                )
            assert await service.list(profile_id) == []
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_store_rejects_profile_id_path_traversal(tmp_path: Path) -> None:
    store = ArtifactStore(
        tmp_path / "artifact-root", runtime_uid=1000, runtime_gid=1000
    )
    with pytest.raises(ArtifactInvalidName):
        store.profile_dir("../escape")


def test_download_source_rejects_paths_outside_the_downloads_directory(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(
        tmp_path / "artifact-root", runtime_uid=1000, runtime_gid=1000
    )
    with pytest.raises(ArtifactInvalidName):
        store.resolve_download_source("p1", "/exchange/downloads/../uploads/evil")
    with pytest.raises(ArtifactInvalidName):
        store.resolve_download_source("p1", "/etc/passwd")


@pytest.mark.asyncio
async def test_concurrent_uploads_cannot_exceed_artifact_count_quota(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:

        async def attempt(index: int):
            try:
                return await service.upload(
                    profile_id,
                    f"file-{index}.csv",
                    "text/csv",
                    _chunks(b"x"),
                )
            except ArtifactQuotaExceeded:
                return None

        results = await asyncio.gather(*(attempt(index) for index in range(6)))
        registered = [item for item in results if item is not None]
        assert len(registered) == 2
        assert len(await service.list(profile_id)) == 2
        stored = [
            item for item in store.profile_dir(profile_id).rglob("*") if item.is_file()
        ]
        assert len(stored) == 2
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "artifact_id",
    ["../escape", "..", "a/b", "", ".hidden", "../../etc/passwd"],
)
@pytest.mark.asyncio
async def test_artifact_id_must_be_a_single_path_component(
    tmp_path: Path, artifact_id: str
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        with pytest.raises(ArtifactInvalidName):
            await service.get(profile_id, artifact_id)
        with pytest.raises(ArtifactInvalidName):
            store.upload_target(profile_id, artifact_id, "file.csv")
        with pytest.raises(ArtifactInvalidName):
            store.download_target(profile_id, artifact_id, "file.csv")
        with pytest.raises(ArtifactInvalidName):
            store.container_path(profile_id, artifact_id, "file.csv", "upload")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_long_download_filename_is_truncated_and_registered(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        source = downloads / "guid-long"
        source.write_bytes(b"long-name")
        long_name = f"{'a' * 300}.csv"
        result = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(source),
            name=long_name,
            sha256=None,
            size=None,
            content_type=None,
        )
        assert result.artifact is not None
        assert result.reason == "created"
        assert len(result.artifact.name.encode("utf-8")) <= 255
        assert result.artifact.name.endswith(".csv")
        assert Path(result.artifact.storage_path).is_file()
        assert not source.exists()
        assert [item.name for item in await service.list(profile_id)] == [
            result.artifact.name
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checksum_mismatch_is_not_registered(tmp_path: Path) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        source = downloads / "guid"
        source.write_bytes(b"actual")
        result = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(source),
            name="actual.csv",
            sha256=secrets.token_hex(32),
            size=6,
            content_type=None,
        )
        assert result.artifact is None
        assert result.reason == "checksum_mismatch"
        assert await service.list(profile_id) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_missing_download_is_reported_with_reason(tmp_path: Path) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        result = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(downloads / "absent"),
            name="absent.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert result.artifact is None
        assert result.reason == "missing"
        assert await service.list(profile_id) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_size_mismatch_is_reported_with_reason(tmp_path: Path) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        source = downloads / "guid"
        source.write_bytes(b"actual")
        result = await service.ingest_download(
            profile_id,
            runtime_instance_id="i1",
            path=str(source),
            name="actual.csv",
            sha256=None,
            size=999,
            content_type=None,
        )
        assert result.artifact is None
        assert result.reason == "size_mismatch"
        assert source.is_file()
        assert await service.list(profile_id) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_artifact_locks_are_released_after_operations(tmp_path: Path) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        await service.upload(profile_id, "one.csv", "text/csv", _chunks(b"1"))
        assert service.locks_idle
        await service.remove_profile(profile_id)
        assert service.locks_idle
    finally:
        await engine.dispose()


# A40: deletion is a resumable two-phase operation (durable intent first),
# and download ingest only trusts instances known to the profile.


@pytest.mark.asyncio
async def test_delete_failure_keeps_intent_and_retry_completes(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        artifact = await service.upload(
            profile_id, "a.csv", "text/csv", _chunks(b"1")
        )
        real_delete = store.delete
        calls = {"count": 0}

        def flaky_delete(pid: str, storage_path: str | None) -> None:
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("simulated storage failure")
            real_delete(pid, storage_path)

        store.delete = flaky_delete  # type: ignore[method-assign]
        with pytest.raises(OSError):
            await service.delete(profile_id, artifact.id)
        # The intent survived; metadata and file are untouched.
        surviving = await service.get(profile_id, artifact.id)
        assert surviving.delete_requested_at is not None
        assert surviving.storage_path is not None
        assert Path(surviving.storage_path).exists()

        store.delete = real_delete  # type: ignore[method-assign]
        await service.delete(profile_id, artifact.id)
        with pytest.raises(ArtifactNotFound):
            await service.get(profile_id, artifact.id)
        assert not Path(surviving.storage_path).exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pending_deletion_resumes_in_fresh_service(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        artifact = await service.upload(
            profile_id, "a.csv", "text/csv", _chunks(b"1")
        )
        storage_path = artifact.storage_path
        # Simulate a crash after the intent was persisted but before the
        # file/metadata cleanup ran.
        marked = await service.repository.mark_delete_requested(
            profile_id, artifact.id
        )
        assert marked is not None and marked.delete_requested_at is not None

        fresh = ArtifactService(
            service.repository,
            store,
            max_artifact_bytes=64,
            max_artifacts_per_profile=2,
            max_profile_bytes=128,
        )
        assert await fresh.resume_pending_deletions() == 1
        with pytest.raises(ArtifactNotFound):
            await fresh.get(profile_id, artifact.id)
        assert storage_path is not None and not Path(storage_path).exists()
        # Resuming again is a no-op.
        assert await fresh.resume_pending_deletions() == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_with_escaping_recorded_path_keeps_intent(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        artifact = await service.upload(
            profile_id, "a.csv", "text/csv", _chunks(b"1")
        )
        outside = tmp_path / "outside.bin"
        outside.write_bytes(b"do not touch")
        maker = service.repository._session_maker
        async with maker() as session, write_transaction(session):
            row = await session.get(ArtifactModel, artifact.id)
            assert row is not None
            row.storage_path = str(outside)
        with pytest.raises(ArtifactInvalidName):
            await service.delete(profile_id, artifact.id)
        # Nothing outside the profile was removed and the intent remains
        # pending for an operator instead of recursing into directories.
        assert outside.read_bytes() == b"do not touch"
        surviving = await service.get(profile_id, artifact.id)
        assert surviving.delete_requested_at is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_rejects_unknown_instance_and_accepts_history(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        source = downloads / "guid-x"
        source.write_bytes(b"data")

        forged = await service.ingest_download(
            profile_id,
            runtime_instance_id="forged-instance",
            path=str(source),
            name="x.bin",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert forged.artifact is None and forged.reason == "unknown_instance"
        assert await service.list(profile_id) == []
        assert source.exists()  # rejected before any file handling

        # A late report from an instance that exists in the recorded
        # runtime history (no longer the current binding) is accepted.
        maker = service.repository._session_maker
        async with maker() as session, write_transaction(session):
            session.add(
                RuntimeEventModel(
                    event_id="evt-old-instance",
                    profile_id=profile_id,
                    runtime_instance_id="old-instance",
                    event_type="exit",
                    config_version=1,
                    payload="{}",
                    created_at="2026-01-01T00:00:00Z",
                )
            )
        accepted = await service.ingest_download(
            profile_id,
            runtime_instance_id="old-instance",
            path=str(source),
            name="x.bin",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert accepted.artifact is not None and accepted.created is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_db_stage_failure_keeps_intent_and_resume_completes(
    tmp_path: Path,
) -> None:
    """The file stage succeeds but dropping the metadata row fails: the
    intent must survive and a later resume converges (the store delete is
    missing-ok, so re-running it is safe)."""
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        artifact = await service.upload(
            profile_id, "a.csv", "text/csv", _chunks(b"1")
        )
        storage_path = artifact.storage_path
        repo = service.repository
        real_delete_row = repo.delete_artifact
        calls = {"count": 0}

        async def flaky_delete_row(pid: str, aid: str) -> bool:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("simulated DB failure")
            return await real_delete_row(pid, aid)

        repo.delete_artifact = flaky_delete_row  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            await service.delete(profile_id, artifact.id)
        # File stage already happened; intent + metadata row remain.
        assert storage_path is not None and not Path(storage_path).exists()
        surviving = await service.get(profile_id, artifact.id)
        assert surviving.delete_requested_at is not None

        repo.delete_artifact = real_delete_row  # type: ignore[method-assign]
        assert await service.resume_pending_deletions() == 1
        with pytest.raises(ArtifactNotFound):
            await service.get(profile_id, artifact.id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_after_completion_reports_not_found(
    tmp_path: Path,
) -> None:
    """Defined end-state (t021 review f001): while a deletion intent is
    pending, repeats are idempotent; once it completed, another delete
    reports the artifact as not found (API 404)."""
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        artifact = await service.upload(
            profile_id, "a.csv", "text/csv", _chunks(b"1")
        )
        await service.delete(profile_id, artifact.id)
        with pytest.raises(ArtifactNotFound):
            await service.delete(profile_id, artifact.id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_resume_survives_pending_list_failure(tmp_path: Path) -> None:
    """Startup resume is best-effort: if even listing the pending intents
    fails transiently, resume reports zero instead of raising (the
    intents stay persisted for the next start)."""
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        repo = service.repository
        real_list = repo.list_pending_deletions

        async def broken_list():
            raise RuntimeError("simulated transient DB failure")

        repo.list_pending_deletions = broken_list  # type: ignore[method-assign]
        assert await service.resume_pending_deletions() == 0
        repo.list_pending_deletions = real_list  # type: ignore[method-assign]
    finally:
        await engine.dispose()
