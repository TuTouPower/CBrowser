"""A5: font-set integrity scan must run off the API event loop.

Proof-of-gap and regression tests: a slow/hung synchronous scan must not
freeze the event loop, the scan must execute on a worker thread, concurrent
scans must be bounded, and content integrity must be re-checked on every
request (no set_id cache, so tampering is reported)."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest
from cbrowser import font_sets as font_sets_pkg
from cbrowser.api.v1 import font_sets_router
from cbrowser.font_sets import import_font_set, manifest


class _FakeService:
    def __init__(self) -> None:
        self.usage_calls = 0

    async def font_set_usage_counts(self) -> dict:
        self.usage_calls += 1
        return {}


@pytest.fixture
def fonts(tmp_path: Path, monkeypatch):
    source = tmp_path / "src"
    source.mkdir()
    (source / "arial.ttf").write_bytes(b"FONT:arial")
    (source / "calibri.ttf").write_bytes(b"FONT:calibri")
    root = tmp_path / "fonts"
    result = import_font_set(
        "windows", [str(source)], "win11-test", root=str(root)
    )
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(root))
    return {
        "root": root,
        "source": source,
        "set_id": result["set_id"],
        "set_dir": Path(result["dir"]),
    }


@pytest.mark.asyncio
async def test_a5_scan_runs_off_event_loop(monkeypatch, fonts) -> None:
    loop_thread = threading.get_ident()
    scan_threads: list[int] = []
    original = font_sets_pkg.list_font_sets

    def recording_scan(*args, **kwargs):
        scan_threads.append(threading.get_ident())
        return original(*args, **kwargs)

    monkeypatch.setattr(font_sets_pkg, "list_font_sets", recording_scan)
    result = await font_sets_router.list_font_sets(_FakeService())
    assert result
    assert scan_threads
    assert all(tid != loop_thread for tid in scan_threads)


@pytest.mark.asyncio
async def test_a5_slow_scan_does_not_block_event_loop(monkeypatch, fonts) -> None:
    started = threading.Event()
    release = threading.Event()
    original_hash = manifest._sha256_file

    def slow_hash(path):
        started.set()
        release.wait(timeout=5)
        return original_hash(path)

    monkeypatch.setattr(manifest, "_sha256_file", slow_hash)

    progress: list[int] = []
    observed: dict[str, int] = {}

    async def heartbeat():
        while True:
            progress.append(1)
            await asyncio.sleep(0.002)

    def watchdog():
        started.wait(timeout=5)
        before = len(progress)
        time.sleep(0.15)
        observed["during"] = len(progress) - before
        release.set()

    hb = asyncio.create_task(heartbeat())
    wd = threading.Thread(target=watchdog, daemon=True)
    wd.start()
    task = asyncio.create_task(
        font_sets_router.list_font_sets(_FakeService())
    )
    try:
        await asyncio.wait_for(task, timeout=5.0)
    finally:
        release.set()
        wd.join(timeout=2.0)
        hb.cancel()
        try:
            await hb
        except asyncio.CancelledError:
            pass
    assert observed.get("during", 0) > 5


@pytest.mark.asyncio
async def test_a5_concurrent_scans_are_bounded(monkeypatch) -> None:
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    def slow_scan(*args, **kwargs):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.03)
        with lock:
            state["active"] -= 1
        return []

    monkeypatch.setattr(font_sets_pkg, "list_font_sets", slow_scan)
    await asyncio.gather(
        *[
            font_sets_router.list_font_sets(_FakeService())
            for _ in range(10)
        ]
    )
    assert state["peak"] >= 1
    assert state["peak"] <= 2


@pytest.mark.asyncio
async def test_a5_tamper_is_reported_on_each_request(monkeypatch, fonts) -> None:
    service = _FakeService()
    first = await font_sets_router.list_font_sets(service)
    assert first
    assert first[0].integrity.ok is True
    assert first[0].integrity.hash_mismatches == []
    assert service.usage_calls == 1

    (fonts["set_dir"] / "arial.ttf").write_bytes(b"TAMPERED")

    second = await font_sets_router.list_font_sets(service)
    assert second[0].integrity.ok is False
    assert second[0].integrity.hash_mismatches == ["arial.ttf"]
    assert service.usage_calls == 2
