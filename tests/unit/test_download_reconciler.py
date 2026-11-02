"""Download completion checksum, directory reconciliation and Supervisor forwarding."""

from __future__ import annotations

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

    import asyncio

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

    import asyncio

    first, second = asyncio.run(run())
    assert first == 1
    assert second == 0
    assert calls[0]["path"] == str(source)
    assert calls[0]["sha256"] == digest
    assert calls[0]["name"] == "report.csv"


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

    import asyncio

    assert asyncio.run(run()) == 1
    assert [call["event_id"] for call in calls] == ["dl_completed_old"]


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

    import asyncio

    assert asyncio.run(run()) == (0, 1)
    assert calls == [401, 200]
