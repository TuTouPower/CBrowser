"""Download completion checksum, directory reconciliation and Supervisor forwarding."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

import httpx
import pytest
from cbrowser.runtime_agent.cdp_proxy import CdpProxyManager
from cbrowser.runtime_agent.download_reconciler import scan_completed_downloads
from cbrowser.runtime_agent.event_storage import EventStorage
from cbrowser.supervisor.artifact_forwarder import (
    DownloadArtifactForwarder,
    translate_download_path,
)


def test_scan_backfills_completed_files_and_excludes_temporary(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    payload = b"store_id,orders\n1,2\n"
    (downloads / "guid-1").write_bytes(payload)
    (downloads / "guid-2.crdownload").write_bytes(b"partial")
    (downloads / ".incoming-x").write_bytes(b"partial")
    storage = EventStorage(tmp_path / "runtime")

    async def run():
        first = await scan_completed_downloads(downloads, "p1", "i1", storage)
        second = await scan_completed_downloads(downloads, "p1", "i1", storage)
        return first, second

    first, second = asyncio.run(run())
    assert len(first) == 1
    assert second == []
    event = first[0]
    assert event.sha256 == hashlib.sha256(payload).hexdigest()
    assert event.size_bytes == len(payload)
    assert event.suggested_filename == "guid-1"
    assert storage.get_download_events()[0].event_id == event.event_id


@pytest.mark.asyncio
async def test_cdp_completion_event_carries_checksum(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    payload = b"payload"
    path = downloads / "guid"
    path.write_bytes(payload)
    storage = EventStorage(tmp_path / "runtime")
    manager = CdpProxyManager(
        browser_ws_url="ws://127.0.0.1:1/devtools/browser/x",
        default_download_dir=downloads,
        profile_id="p1",
        runtime_instance_id="i1",
        event_storage=storage,
    )
    manager.active_downloads["guid"] = {
        "guid": "guid",
        "url": "https://example.test/file",
        "suggested_filename": "report.csv",
        "download_path": str(path),
        "state": "in_progress",
    }
    await manager._handle_download_progress(
        {
            "guid": "guid",
            "state": "completed",
            "receivedBytes": len(payload),
            "totalBytes": len(payload),
            "filePath": str(path),
        }
    )
    event = storage.get_download_events()[0]
    assert event.state == "completed"
    assert event.sha256 == hashlib.sha256(payload).hexdigest()
    assert event.size_bytes == len(payload)


def test_supervisor_translates_container_path_and_forwards_once(
    tmp_path: Path,
) -> None:
    assert translate_download_path("/exchange/downloads/guid", tmp_path, "p1") == str(
        tmp_path / "artifacts" / "p1" / "downloads" / "guid"
    )

    data_root = tmp_path / "data"
    downloads = data_root / "artifacts" / "p1" / "downloads"
    downloads.mkdir(parents=True)
    source = downloads / "guid"
    source.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    events = data_root / "runtime-events" / "p1" / "events" / "downloads"
    events.mkdir(parents=True)
    event = {
        "event_id": "dl_completed_1",
        "profile_id": "p1",
        "runtime_instance_id": "i1",
        "guid": "guid",
        "suggested_filename": "report.csv",
        "download_path": "/exchange/downloads/guid",
        "state": "completed",
        "received_bytes": 7,
        "total_bytes": 7,
        "size_bytes": 7,
        "sha256": digest,
    }
    (events / "dl_completed_1.json").write_text(json.dumps(event), encoding="utf-8")

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok", "outcome": "created"})

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://api"
        ) as client:
            forwarder = DownloadArtifactForwarder(data_root, client)
            first = await forwarder.forward_pending()
            second = await forwarder.forward_pending()
            return first, second

    first, second = asyncio.run(run())
    assert first == 1
    assert second == 0
    assert calls[0]["path"] == "/exchange/downloads/guid"
    assert calls[0]["sha256"] == digest
    assert calls[0]["name"] == "report.csv"


def test_translate_download_path_rejects_escapes(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        translate_download_path("/exchange/downloads/../../evil", tmp_path, "p1")
    with pytest.raises(ValueError):
        translate_download_path("/exchange/downloads/guid", tmp_path, "../p1")
    with pytest.raises(ValueError):
        translate_download_path("/etc/passwd", tmp_path, "p1")


def test_forwarder_dead_letters_unparseable_event(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    events = data_root / "runtime-events" / "p1" / "events" / "downloads"
    events.mkdir(parents=True)
    (events / "broken.json").write_text("{not-json", encoding="utf-8")

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok", "outcome": "created"})

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://api"
        ) as client:
            return await DownloadArtifactForwarder(data_root, client).forward_pending()

    assert asyncio.run(run()) == 0
    assert calls == []
    assert not (events / "broken.json").exists()
    dead_letter = data_root / "control" / "download-dead-letter" / "p1"
    assert len(list(dead_letter.glob("broken.unreadable.*.json"))) == 1


def test_forwarder_dead_letters_profile_mismatch(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    downloads = data_root / "artifacts" / "p1" / "downloads"
    downloads.mkdir(parents=True)
    (downloads / "guid").write_bytes(b"payload")
    events = data_root / "runtime-events" / "p1" / "events" / "downloads"
    events.mkdir(parents=True)
    event = {
        "event_id": "dl_other_profile",
        "profile_id": "p2",
        "runtime_instance_id": "i1",
        "guid": "guid",
        "download_path": "/exchange/downloads/guid",
        "state": "completed",
        "received_bytes": 7,
        "total_bytes": 7,
        "size_bytes": 7,
    }
    (events / "event.json").write_text(json.dumps(event), encoding="utf-8")

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok", "outcome": "created"})

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://api"
        ) as client:
            return await DownloadArtifactForwarder(data_root, client).forward_pending()

    assert asyncio.run(run()) == 0
    assert calls == []
    dead_letter = data_root / "control" / "download-dead-letter" / "p1"
    assert len(list(dead_letter.glob("event.profile_mismatch.*.json"))) == 1


def test_forwarder_dead_letters_unsupported_envelope_version(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    downloads = data_root / "artifacts" / "p1" / "downloads"
    downloads.mkdir(parents=True)
    (downloads / "guid").write_bytes(b"payload")
    events = data_root / "runtime-events" / "p1" / "events" / "downloads"
    events.mkdir(parents=True)
    event = {
        "version": 99,
        "event_id": "dl_future",
        "profile_id": "p1",
        "runtime_instance_id": "i1",
        "guid": "guid",
        "download_path": "/exchange/downloads/guid",
        "state": "completed",
        "received_bytes": 7,
        "total_bytes": 7,
        "size_bytes": 7,
    }
    (events / "event.json").write_text(json.dumps(event), encoding="utf-8")

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok", "outcome": "created"})

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://api"
        ) as client:
            return await DownloadArtifactForwarder(data_root, client).forward_pending()

    assert asyncio.run(run()) == 0
    assert calls == []
    dead_letter = data_root / "control" / "download-dead-letter" / "p1"
    assert len(list(dead_letter.glob("event.unsupported_version.*.json"))) == 1


def test_forwarder_dead_letters_path_escape(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    events = data_root / "runtime-events" / "p1" / "events" / "downloads"
    events.mkdir(parents=True)
    event = {
        "event_id": "dl_escape",
        "profile_id": "p1",
        "runtime_instance_id": "i1",
        "guid": "guid",
        "download_path": "/exchange/downloads/../../evil",
        "state": "completed",
        "received_bytes": 7,
        "total_bytes": 7,
        "size_bytes": 7,
    }
    (events / "event.json").write_text(json.dumps(event), encoding="utf-8")

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok", "outcome": "created"})

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://api"
        ) as client:
            return await DownloadArtifactForwarder(data_root, client).forward_pending()

    assert asyncio.run(run()) == 0
    assert calls == []
    dead_letter = data_root / "control" / "download-dead-letter" / "p1"
    assert len(list(dead_letter.glob("event.path_escape.*.json"))) == 1


def test_forwarder_does_not_skip_older_completed_events(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    downloads = data_root / "artifacts" / "p1" / "downloads"
    downloads.mkdir(parents=True)
    source = downloads / "guid-old"
    source.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    events = data_root / "runtime-events" / "p1" / "events" / "downloads"
    events.mkdir(parents=True)
    begin = {
        "event_id": "dl_begin_new",
        "profile_id": "p1",
        "runtime_instance_id": "i1",
        "guid": "guid-new",
        "download_path": "/exchange/downloads/guid-new",
        "state": "in_progress",
        "received_bytes": 1,
        "total_bytes": 1,
    }
    completed = {
        "event_id": "dl_completed_old",
        "profile_id": "p1",
        "runtime_instance_id": "i1",
        "guid": "guid-old",
        "suggested_filename": "old.csv",
        "download_path": "/exchange/downloads/guid-old",
        "state": "completed",
        "received_bytes": 7,
        "total_bytes": 7,
        "size_bytes": 7,
        "sha256": digest,
    }
    begin_file = events / "a_begin.json"
    completed_file = events / "b_completed.json"
    begin_file.write_text(json.dumps(begin), encoding="utf-8")
    completed_file.write_text(json.dumps(completed), encoding="utf-8")
    os.utime(begin_file, ns=(200, 200))
    os.utime(completed_file, ns=(100, 100))

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok", "outcome": "created"})

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://api"
        ) as client:
            forwarder = DownloadArtifactForwarder(data_root, client)
            return await forwarder.forward_pending()

    assert asyncio.run(run()) == 1
    assert [call["event_id"] for call in calls] == ["dl_completed_old"]


def test_forwarder_truncates_overlong_filename_before_delivery(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    downloads = data_root / "artifacts" / "p1" / "downloads"
    downloads.mkdir(parents=True)
    source = downloads / "guid"
    source.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    events = data_root / "runtime-events" / "p1" / "events" / "downloads"
    events.mkdir(parents=True)
    long_name = f"{'a' * 300}.csv"
    event = {
        "event_id": "dl_completed_long",
        "profile_id": "p1",
        "runtime_instance_id": "i1",
        "guid": "guid",
        "suggested_filename": long_name,
        "download_path": "/exchange/downloads/guid",
        "state": "completed",
        "received_bytes": 7,
        "total_bytes": 7,
        "size_bytes": 7,
        "sha256": digest,
    }
    (events / "event.json").write_text(json.dumps(event), encoding="utf-8")

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok", "outcome": "created"})

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://api"
        ) as client:
            forwarder = DownloadArtifactForwarder(data_root, client)
            first = await forwarder.forward_pending()
            second = await forwarder.forward_pending()
            return first, second

    assert asyncio.run(run()) == (1, 0)
    assert len(calls[0]["name"]) <= 255
    assert calls[0]["name"]


def test_forwarder_retries_after_retryable_4xx(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    downloads = data_root / "artifacts" / "p1" / "downloads"
    downloads.mkdir(parents=True)
    source = downloads / "guid"
    source.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    events = data_root / "runtime-events" / "p1" / "events" / "downloads"
    events.mkdir(parents=True)
    event = {
        "event_id": "dl_completed_retry",
        "profile_id": "p1",
        "runtime_instance_id": "i1",
        "guid": "guid",
        "suggested_filename": "retry.csv",
        "download_path": "/exchange/downloads/guid",
        "state": "completed",
        "received_bytes": 7,
        "total_bytes": 7,
        "size_bytes": 7,
        "sha256": digest,
    }
    (events / "event.json").write_text(json.dumps(event), encoding="utf-8")
    statuses = [401, 200]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses[len(calls)]
        calls.append(status)
        return httpx.Response(status, json={"status": "ok"})

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://api"
        ) as client:
            forwarder = DownloadArtifactForwarder(data_root, client)
            first = await forwarder.forward_pending()
            second = await forwarder.forward_pending()
            return first, second

    assert asyncio.run(run()) == (0, 1)
    assert calls == [401, 200]


def _write_download_event(
    data_root: Path, profile_id: str, instance_id: str, event_id: str
) -> Path:
    downloads = data_root / "artifacts" / profile_id / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    (downloads / f"guid-{event_id}").write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    events = data_root / "runtime-events" / profile_id / "events" / "downloads"
    events.mkdir(parents=True, exist_ok=True)
    event = {
        "event_id": event_id,
        "profile_id": profile_id,
        "runtime_instance_id": instance_id,
        "guid": f"guid-{event_id}",
        "suggested_filename": "report.csv",
        "download_path": f"/exchange/downloads/guid-{event_id}",
        "state": "completed",
        "received_bytes": 7,
        "total_bytes": 7,
        "size_bytes": 7,
        "sha256": digest,
    }
    target = events / f"{event_id}.json"
    target.write_text(json.dumps(event), encoding="utf-8")
    return target


def _ok_client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "outcome": "created"})

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://api"
    )


def _cursor_file(data_root: Path) -> dict:
    path = data_root / "control" / "download_cursors.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def test_forwarder_prunes_cursors_for_vanished_instances(tmp_path: Path) -> None:
    """AC-006 (A12): after one complete successful scan, cursors of
    instances that disappeared from the event tree are cleared; instances
    still present keep theirs, and a restart reloads the pruned state."""
    data_root = tmp_path / "data"
    gone_file = _write_download_event(data_root, "p1", "i-gone", "dl_gone")
    _write_download_event(data_root, "p1", "i-stays", "dl_stays")

    async def run(forwarder: DownloadArtifactForwarder) -> int:
        return await forwarder.forward_pending()

    async def first_pass() -> int:
        async with _ok_client() as client:
            return await DownloadArtifactForwarder(data_root, client).forward_pending()

    assert asyncio.run(first_pass()) == 2
    cursors = _cursor_file(data_root)
    assert set(cursors["p1"]) == {"i-gone", "i-stays"}

    gone_file.unlink()

    async def second_pass() -> int:
        async with _ok_client() as client:
            # A fresh forwarder models a process restart reloading cursors.
            return await DownloadArtifactForwarder(data_root, client).forward_pending()

    assert asyncio.run(second_pass()) == 0
    cursors = _cursor_file(data_root)
    assert set(cursors.get("p1", {})) == {"i-stays"}
    assert cursors["p1"]["i-stays"] == ["dl_stays"]


def test_forwarder_keeps_cursors_when_profile_scan_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-006 (A12): a read failure is not an empty tree — cursors of the
    failed profile survive pruning while other profiles prune normally."""
    data_root = tmp_path / "data"
    _write_download_event(data_root, "p1", "i-keep", "dl_keep")
    gone = _write_download_event(data_root, "p2", "i-gone", "dl_gone2")

    async def first_pass() -> int:
        async with _ok_client() as client:
            return await DownloadArtifactForwarder(data_root, client).forward_pending()

    assert asyncio.run(first_pass()) == 2
    gone.unlink()

    real_glob = Path.glob

    def flaky_glob(self: Path, pattern: str):
        if self.name == "downloads" and "p1" in self.parts:
            raise OSError("simulated scan failure")
        return real_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", flaky_glob)

    async def second_pass() -> int:
        async with _ok_client() as client:
            return await DownloadArtifactForwarder(data_root, client).forward_pending()

    assert asyncio.run(second_pass()) == 0
    cursors = _cursor_file(data_root)
    assert cursors["p1"]["i-keep"] == ["dl_keep"]
    assert "p2" not in cursors


def test_recovery_coordinator_uses_shared_singleton_lock_names() -> None:
    """AC-006 (A12): one lock-file identity for normal start and recovery."""
    from cbrowser.supervisor import recovery_coordinator
    from cbrowser.supervisor.volume_spec import SINGLETON_LOCK_NAMES

    assert recovery_coordinator.SINGLETON_LOCK_NAMES is SINGLETON_LOCK_NAMES
    assert SINGLETON_LOCK_NAMES == (
        "SingletonLock",
        "SingletonCookie",
        "SingletonSocket",
    )
