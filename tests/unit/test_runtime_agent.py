"""Unit tests for Browser Runtime Agent security, storage, and UDS routing."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.runtime_agent.event_storage import (
    CorruptStateError,
    EventStorage,
    StorageError,
)
from cbrowser.runtime_agent.protocol import (
    DownloadEventRecord,
    RuntimeEventRecord,
    RuntimeStateRecord,
)
from cbrowser.runtime_agent.runner import BrowserRunner
from cbrowser.launch_args import InvalidLaunchArgument, validate_launch_args
from cbrowser.runtime_agent.subsystems import check_audio, check_browser, check_display


def test_launch_args_whitelist_contract() -> None:
    safe = ["--no-first-run", "--lang=en-US", "--accept-lang=en-US,zh-CN"]
    assert validate_launch_args(safe) == safe

    for arg in (
        "--load-extension=/tmp/evil",
        "--js-flags=--noopt",
        "file:///etc/passwd",
        "--fingerprint=123",
        "--window-size=800,600",
        "--no-sandbox",
        "--disable-web-security",
    ):
        with pytest.raises(InvalidLaunchArgument):
            validate_launch_args([arg])


def test_event_storage_atomic_write_and_recovery(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)

    evt1 = RuntimeEventRecord(
        event_id="evt_01",
        profile_id="p1",
        runtime_instance_id="i1",
        event_type="exit",
        exit_code=0,
        exit_reason="normal",
        config_version=1,
    )
    evt2 = RuntimeEventRecord(
        event_id="evt_02",
        profile_id="p1",
        runtime_instance_id="i1",
        event_type="lifecycle",
        config_version=1,
    )
    storage.save_runtime_event(evt1)
    storage.save_runtime_event(evt2)

    loaded_events = storage.get_runtime_events()
    assert len(loaded_events) == 2
    assert loaded_events[0].event_id == "evt_01"
    assert loaded_events[1].event_id == "evt_02"

    dl1 = DownloadEventRecord(
        event_id="dl_01",
        profile_id="p1",
        runtime_instance_id="i1",
        guid="guid-abc",
        state="completed",
        received_bytes=2048,
        total_bytes=2048,
    )
    storage.save_download_event(dl1)

    loaded_dls = storage.get_download_events()
    assert len(loaded_dls) == 1
    assert loaded_dls[0].guid == "guid-abc"
    assert loaded_dls[0].state == "completed"

    state = RuntimeStateRecord(
        profile_id="p1",
        runtime_instance_id="i1",
        config_version=1,
        state="stopped",
        exit_code=0,
        exit_reason="normal",
    )
    storage.save_state(state)
    recovered_state = storage.get_state()
    assert recovered_state is not None
    assert recovered_state.state == "stopped"
    assert recovered_state.exit_code == 0


def test_event_storage_corrupt_state_raises_error(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)
    state_file = tmp_path / "state.json"
    state_file.write_text("NOT_VALID_JSON{[[", encoding="utf-8")

    with pytest.raises(CorruptStateError):
        storage.get_state()


def test_event_storage_corrupt_event_raises_error(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)
    bad_evt_file = storage.runtime_events_dir / "bad_evt.json"
    bad_evt_file.write_text("CORRUPT_BYTES", encoding="utf-8")

    with pytest.raises(StorageError):
        storage.get_runtime_events()


@pytest.mark.asyncio
async def test_event_storage_concurrency(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)

    async def write_batch(prefix: str, count: int) -> None:
        for i in range(count):
            evt = RuntimeEventRecord(
                event_id=f"evt_{prefix}_{i:03d}",
                profile_id="p1",
                runtime_instance_id="i1",
                event_type="exit",
                exit_code=0,
                config_version=1,
            )
            storage.save_runtime_event(evt)
            await asyncio.sleep(0.001)

    tasks = [asyncio.create_task(write_batch(f"worker_{w}", 10)) for w in range(5)]
    await asyncio.gather(*tasks)

    all_events = storage.get_runtime_events()
    assert len(all_events) == 50, f"Expected 50 events, found {len(all_events)}"


def test_event_storage_dirfsync_failure_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject directory fsync failures with StorageError."""
    import errno
    from unittest.mock import patch

    def mock_fsync(fd: int) -> None:
        raise OSError(errno.EIO, "Input/output error")

    storage = EventStorage(tmp_path)
    evt = RuntimeEventRecord(
        event_id="evt_fail",
        profile_id="p1",
        runtime_instance_id="i1",
        event_type="exit",
        exit_code=0,
        config_version=1,
    )
    with patch("os.fsync", side_effect=mock_fsync), pytest.raises(StorageError):
        storage.save_runtime_event(evt)


def test_subsystem_checks_negative(tmp_path: Path) -> None:
    ok, msg = check_display(":9999", None)
    assert not ok
    assert "socket not found" in msg

    fake_sock = tmp_path / "pulse.sock"
    fake_cookie = tmp_path / "pulse.cookie"
    ok, msg = check_audio(fake_sock, fake_cookie)
    assert not ok
    assert "socket not found" in msg

    fake_sock.touch()
    fake_cookie.write_bytes(b"short_cookie")
    ok, msg = check_audio(fake_sock, fake_cookie)
    assert not ok
    assert "Invalid PulseAudio cookie size" in msg

    ok, msg = check_browser(cdp_port=0, browser_pid=99999999)
    assert not ok


def test_runner_snapshot_validation_failures(tmp_path: Path) -> None:
    # 1. Non-existent snapshot file
    with pytest.raises(ValueError, match="Config snapshot file not found"):
        BrowserRunner(
            profile_id="p1",
            runtime_instance_id="i1",
            config_snapshot_path=tmp_path / "missing.json",
            run_dir=tmp_path / "run",
            user_data_dir=tmp_path / "user_data",
        )

    # 2. Corrupt JSON in snapshot
    corrupt_snap = tmp_path / "corrupt.json"
    corrupt_snap.write_text("{corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid config snapshot format"):
        BrowserRunner(
            profile_id="p1",
            runtime_instance_id="i1",
            config_snapshot_path=corrupt_snap,
            run_dir=tmp_path / "run",
            user_data_dir=tmp_path / "user_data",
        )

    # 3. Profile ID mismatch
    valid_p2 = ConfigVersionSnapshot(
        id="snap_01",
        profile_id="p2",
        version=1,
        config=ProfileConfig(name="Profile Two").model_dump(),
        created_at="2026-10-28T00:00:00Z",
    )
    p2_snap = tmp_path / "p2_snap.json"
    p2_snap.write_text(json.dumps(valid_p2.model_dump()), encoding="utf-8")

    with pytest.raises(ValueError, match="profile_id mismatch"):
        BrowserRunner(
            profile_id="p1",  # runner asks for p1, but snapshot is for p2!
            runtime_instance_id="i1",
            config_snapshot_path=p2_snap,
            run_dir=tmp_path / "run",
            user_data_dir=tmp_path / "user_data",
        )


@pytest.mark.asyncio
async def test_agent_app_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True, exist_ok=True)
    download_dir = tmp_path / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)

    # Prepare runner_info.json
    runner_info = {
        "profile_id": "test_profile",
        "runtime_instance_id": "test_instance",
        "config_version": 2,
        "cdp_port": 9222,
        "browser_ws_url": "ws://127.0.0.1:9222/cdp",
        "display": ":99",
        "pulse_sock": str(run_dir / "pulse.sock"),
        "pulse_cookie": str(run_dir / "pulse.cookie"),
        "browser_pid": 1234,
        "runner_pid": 5678,
    }
    (run_dir / "runner_info.json").write_text(json.dumps(runner_info), encoding="utf-8")

    mock_cdp = MagicMock()
    mock_cdp.rearm_count = 1
    mock_cdp.close_browser = AsyncMock(return_value={"closed": True})
    mock_cdp.rearm_download_capture = AsyncMock()

    app = create_agent_app(
        run_dir=run_dir,
        default_download_dir=download_dir,
        cdp_proxy=mock_cdp,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Config version endpoint
        resp = await client.get("/config_version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["profile_id"] == "test_profile"
        assert data["config_version"] == 2

        # Health endpoint (when display/audio sockets do not exist, ready must be False)
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        hdata = health_resp.json()
        assert hdata["ready"] is False
        assert hdata["status"] in ("degraded", "error")

        # Control endpoint: valid 'close'
        ctrl_resp = await client.post("/control", json={"action": "close"})
        assert ctrl_resp.status_code == 200
        assert ctrl_resp.json()["status"] == "ok"
        mock_cdp.close_browser.assert_called_once()

        # Control endpoint: valid 'rearm_downloads'
        rearm_resp = await client.post("/control", json={"action": "rearm_downloads"})
        assert rearm_resp.status_code == 200
        assert rearm_resp.json()["status"] == "ok"
        mock_cdp.rearm_download_capture.assert_called_once()

        # Control endpoint: invalid action -> 400
        bad_ctrl = await client.post("/control", json={"action": "rm -rf /"})
        assert bad_ctrl.status_code in (400, 422)

        # Health probes run concurrently off the event loop.  Concurrency
        # is proven structurally (t024 AC-007/A28): the three probe
        # intervals must overlap, which is impossible if they ran serially
        # -- no wall-clock budget is asserted.
        from cbrowser.runtime_agent import agent as agent_module

        intervals: list[tuple[float, float]] = []

        def slow_probe(*_args, **_kwargs):
            start = time.monotonic()
            time.sleep(0.25)
            intervals.append((start, time.monotonic()))
            return True, "ok"

        monkeypatch.setattr(agent_module, "check_display", slow_probe)
        monkeypatch.setattr(agent_module, "check_audio", slow_probe)
        monkeypatch.setattr(agent_module, "check_browser", slow_probe)
        fast_health = await client.get("/health")
        assert fast_health.status_code == 200
        assert len(intervals) == 3
        assert max(start for start, _end in intervals) < min(
            end for _start, end in intervals
        ), f"health probes did not overlap: {intervals}"

        # Events endpoints
        evts_resp = await client.get("/events/runtime")
        assert evts_resp.status_code == 200
        assert isinstance(evts_resp.json(), list)

        dls_resp = await client.get("/events/downloads")
        assert dls_resp.status_code == 200
        assert isinstance(dls_resp.json(), list)


@pytest.mark.asyncio
async def test_agent_app_offline_replay_mode(tmp_path: Path) -> None:
    """Agent initializes in offline replay mode when terminal state is detected."""
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True, exist_ok=True)
    storage = EventStorage(run_dir)

    # Persist terminal state
    storage.save_state(
        RuntimeStateRecord(
            profile_id="p_term",
            runtime_instance_id="i_term",
            config_version=1,
            state="stopped",
            exit_code=0,
            exit_reason="normal",
        )
    )

    # create app without live cdp_proxy
    app = create_agent_app(
        run_dir=run_dir,
        default_download_dir=tmp_path / "dl",
        cdp_proxy=None,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Config version still responds from state
        resp = await client.get("/config_version")
        assert resp.status_code == 200
        assert resp.json()["profile_id"] == "p_term"

        # Health reports stopped in details
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["ready"] is False
        assert health.json()["details"]["state"] == "stopped"

        # Events endpoint works and replays events
        evts = await client.get("/events/runtime")
        assert evts.status_code == 200
