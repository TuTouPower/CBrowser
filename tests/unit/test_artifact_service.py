"""Artifact storage/service behavior: atomicity, quota, MIME and reconciliation."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.artifact_repository import ArtifactRepository
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.adapters.filesystem.artifact_store import (
    ArtifactInsufficientStorage,
    ArtifactInvalidContentType,
    ArtifactInvalidName,
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
    profile = await ProfileRepository(maker).create_profile(
        ProfileConfig(name="Artifacts", fingerprint_seed=1)
    )
    store = ArtifactStore(tmp_path / "artifact-root")
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
async def test_quota_and_mime_are_enforced(tmp_path: Path) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        with pytest.raises(ArtifactInvalidContentType):
            await service.upload(
                profile_id, "bad.sh", "application/x-sh", _chunks(b"rm -rf /")
            )
        await service.upload(profile_id, "one.csv", "text/csv", _chunks(b"1"))
        await service.upload(profile_id, "two.csv", "text/csv", _chunks(b"2"))
        with pytest.raises(ArtifactQuotaExceeded):
            await service.upload(profile_id, "three.csv", "text/csv", _chunks(b"3"))
    finally:
        await engine.dispose()


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
            path=str(source),
            name="orders.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert first is not None and first[1] is True
        canonical = Path(first[0].storage_path)
        assert canonical.read_bytes() == payload
        assert not source.exists()

        second = await service.ingest_download(
            profile_id,
            path=str(canonical),
            name="orders.csv",
            sha256=first[0].sha256,
            size=len(payload),
            content_type=None,
        )
        assert second is not None and second[1] is False
        assert second[0].id == first[0].id
        assert await service.list(profile_id) == [first[0]]

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
            path=str(first_source),
            name="first.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        second = await service.ingest_download(
            profile_id,
            path=str(second_source),
            name="second.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert first is not None and first[1] is True
        assert second is not None and second[1] is True
        assert first[0].sha256 == second[0].sha256
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
            path=str(first_source),
            name="report.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        second = await service.ingest_download(
            profile_id,
            path=str(second_source),
            name="report.csv",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert first is not None and first[1] is True
        assert second is not None and second[1] is True
        assert first[0].id != second[0].id
        assert len(await service.list(profile_id)) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_executable_download_is_registered_as_octet_stream(
    tmp_path: Path,
) -> None:
    engine, store, service, profile_id = await _context(tmp_path)
    try:
        downloads = store.downloads_dir(profile_id)
        downloads.mkdir(parents=True, exist_ok=True)
        source = downloads / "guid"
        source.write_bytes(b"MZ")
        created = await service.ingest_download(
            profile_id,
            path=str(source),
            name="installer.exe",
            sha256=None,
            size=None,
            content_type=None,
        )
        assert created is not None and created[1] is True
        assert created[0].content_type == "application/octet-stream"
        assert created[0].name == "installer.exe"
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


def test_uploaded_file_is_readable_by_runtime_user(tmp_path: Path) -> None:
    import asyncio

    async def run():
        engine, store, service, profile_id = await _context(tmp_path)
        try:
            artifact = await service.upload(
                profile_id, "readable.csv", "text/csv", _chunks(b"hello")
            )
            path = Path(artifact.storage_path)
            file_mode = path.stat().st_mode & 0o777
            dir_mode = path.parent.stat().st_mode & 0o777
            assert file_mode & 0o040
            assert dir_mode & 0o050
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_store_rejects_profile_id_path_traversal(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifact-root")
    with pytest.raises(ArtifactInvalidName):
        store.profile_dir("../escape")


def test_download_source_rejects_paths_outside_the_downloads_directory(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path / "artifact-root")
    with pytest.raises(ArtifactInvalidName):
        store.resolve_download_source("p1", "/exchange/downloads/../uploads/evil")
    with pytest.raises(ArtifactInvalidName):
        store.resolve_download_source("p1", "/etc/passwd")


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
            path=str(source),
            name="actual.csv",
            sha256=secrets.token_hex(32),
            size=6,
            content_type=None,
        )
        assert result is None
        assert await service.list(profile_id) == []
    finally:
        await engine.dispose()
