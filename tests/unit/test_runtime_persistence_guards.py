"""Runtime boundary regressions using actual storage and validation paths."""

from __future__ import annotations

import errno
import json
import logging
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from cbrowser.runtime_agent.event_storage import StorageError, atomic_write_json
from cbrowser.runtime_agent.protocol import RuntimeEventRecord
from cbrowser.runtime_agent.runner import BrowserRunner
from cbrowser.launch_args import InvalidLaunchArgument, validate_launch_args
from cloakbrowser.config import PLATFORM_CHROMIUM_VERSIONS


def make_runner(
    root: Path, *, profile_id: str = "profile_a", version: int = 1
) -> BrowserRunner:
    snapshot = root / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "id": "snapshot_a",
                "profile_id": profile_id,
                "version": version,
                "config": {"name": "Runtime guard regression"},
                "created_at": "2026-10-28T10:00:00+08:00",
            }
        )
    )
    return BrowserRunner(
        profile_id,
        "instance_a",
        snapshot,
        root / "runtime",
        root / "profile",
        events_dir=root / "events",
        engine_cache_dir=root / "engine_cache",
    )


@pytest.mark.parametrize("error_number", [errno.EIO, errno.EINVAL, errno.ENOTSUP])
def test_directory_sync_failure_never_acknowledges_durability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    # Targeted fault injection: actual JSON serialization, file fsync and replace
    # run; only the otherwise unavailable kernel directory failure is injected.
    real_fsync = os.fsync

    def fail_directory_sync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(error_number, "injected directory synchronization failure")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_sync)
    with pytest.raises(StorageError):
        atomic_write_json(tmp_path / "event.json", {"event_id": "event_a"})


def test_rejected_launch_argument_does_not_enter_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "private_proxy_argument_canary_726f1d"
    with caplog.at_level(logging.WARNING):
        with pytest.raises(InvalidLaunchArgument):
            validate_launch_args([f"--proxy-server={canary}\x01tail"])
    assert canary not in caplog.text


@pytest.mark.parametrize(
    "features", ["IsolateOrigins", "Other,IsolateOrigins", "IsolateOrigins,Other"]
)
def test_disable_features_override_is_rejected(features: str) -> None:
    with pytest.raises(InvalidLaunchArgument):
        validate_launch_args([f"--disable-features={features}"])


def test_non_whitelisted_feature_option_is_rejected() -> None:
    with pytest.raises(InvalidLaunchArgument):
        validate_launch_args(["--disable-features=UnrelatedFeature"])


@pytest.mark.parametrize(
    "profile_id,version",
    [
        ("profile_a", 0),
        ("profile_a", -1),
        ("../escape_profile", 1),
        ("..", 1),
    ],
)
def test_invalid_runtime_identity_rejected_before_storage_creation(
    tmp_path: Path,
    profile_id: str,
    version: int,
) -> None:
    with pytest.raises(ValueError):
        make_runner(tmp_path, profile_id=profile_id, version=version)
    assert not (tmp_path / "events").exists()
    assert not (tmp_path / "runtime").exists()


@pytest.mark.asyncio
async def test_terminal_event_prevents_relaunch_even_if_state_write_was_lost(
    tmp_path: Path,
) -> None:
    runner = make_runner(tmp_path)
    runner.event_storage.save_runtime_event(
        RuntimeEventRecord(
            event_id="exit_event_a",
            profile_id="profile_a",
            runtime_instance_id="instance_a",
            config_version=1,
            event_type="exit",
            exit_code=0,
            exit_reason="normal",
        )
    )
    # Cache is intentionally absent. Replaying a durable terminal fact must
    # finish before binary resolution or any display/browser/audio startup.
    await runner.start()
    assert not runner.is_running
    assert not (tmp_path / "profile").exists()


@pytest.mark.asyncio
async def test_terminal_storage_failure_propagates_instead_of_reporting_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure is injected at the storage seam (t024 AC-005/A26): patching
    the EventStorage write methods exercises the same propagation path in
    every environment, unlike chmod, which UID 0 bypasses."""
    runner = make_runner(tmp_path)
    exit_status = tmp_path / "exit_code"
    exit_status.write_text("0")
    runner.is_running = True

    def fail_write(*_args, **_kwargs):
        raise StorageError("injected storage failure")

    monkeypatch.setattr(runner.event_storage, "save_state", fail_write)
    monkeypatch.setattr(runner.event_storage, "save_runtime_event", fail_write)
    with pytest.raises(StorageError):
        await runner._wait_for_chrome_exit(exit_status)
    assert runner.event_storage.get_state() is None


@pytest.mark.skipif(
    os.geteuid() == 0,
    reason="permission bits do not block UID 0; seam variant above covers it",
)
@pytest.mark.asyncio
async def test_terminal_storage_failure_via_permissions_propagates(
    tmp_path: Path,
) -> None:
    runner = make_runner(tmp_path)
    exit_status = tmp_path / "exit_code"
    exit_status.write_text("0")
    runner.is_running = True
    event_directory = runner.event_storage.runtime_events_dir
    event_directory.chmod(0o500)
    try:
        with pytest.raises(StorageError):
            await runner._wait_for_chrome_exit(exit_status)
        assert runner.event_storage.get_state() is None
    finally:
        event_directory.chmod(0o700)


def test_engine_cache_does_not_fall_back_to_an_arbitrary_version(
    tmp_path: Path,
) -> None:
    runner = make_runner(tmp_path)
    binary = tmp_path / "engine_cache" / "chromium-0.0.0.0.0" / "chrome"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\x7fELF" + b"\0" * 60)
    binary.chmod(0o700)
    with pytest.raises(RuntimeError):
        runner.resolve_engine_binary()


def test_engine_cache_rejects_wrong_architecture_before_execution(
    tmp_path: Path,
) -> None:
    runner = make_runner(tmp_path)
    target = (
        "linux-arm64"
        if platform.machine().lower() in ("arm64", "aarch64")
        else "linux-x64"
    )
    binary = (
        tmp_path
        / "engine_cache"
        / f"chromium-{PLATFORM_CHROMIUM_VERSIONS[target]}"
        / "chrome"
    )
    binary.parent.mkdir(parents=True)
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    header[18:20] = (62 if target == "linux-arm64" else 183).to_bytes(2, "little")
    binary.write_bytes(header)
    binary.chmod(0o700)
    with pytest.raises(RuntimeError):
        runner.resolve_engine_binary()


def test_module_entrypoint_exposes_standalone_agent_cli() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cbrowser.runtime_agent", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--events-dir" in result.stdout


def test_runner_support_paths_live_inside_the_run_directory(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    run_dir = tmp_path / "runtime"
    assert runner.pulse_dir == run_dir / "pulse"
    assert runner.openbox_dir == run_dir / "openbox"
    assert runner.x11_config_dir == run_dir / "x11-config"


def test_browser_environment_is_explicit_and_does_not_mutate_process(
    tmp_path: Path,
) -> None:
    runner = make_runner(tmp_path)
    before = dict(os.environ)
    run_dir = tmp_path / "runtime"
    env = runner._browser_environment(
        run_dir / "pulse" / "pulse.sock",
        run_dir / "pulse" / "pulse.cookie",
        run_dir / "chrome_wrapper.sh",
    )

    assert dict(os.environ) == before
    assert env["DISPLAY"] == runner.display
    assert env["XAUTHORITY"] == str(runner.xauth_path)
    assert env["PULSE_SERVER"] == f"unix:{run_dir / 'pulse' / 'pulse.sock'}"
    assert env["PULSE_COOKIE"] == str(run_dir / "pulse" / "pulse.cookie")
    assert env["CLOAKBROWSER_BINARY_PATH"] == str(run_dir / "chrome_wrapper.sh")
    assert env["CLOAKBROWSER_CACHE_DIR"] == str(tmp_path / "engine_cache")


def test_x11_lock_owned_by_a_live_process_is_not_removed(tmp_path: Path) -> None:
    lock = tmp_path / ".X99-lock"
    sock = tmp_path / "X99"
    lock.write_text(str(os.getpid()), encoding="utf-8")
    sock.touch()

    with pytest.raises(RuntimeError, match="already in use"):
        BrowserRunner._clear_stale_x11_state(lock, sock)
    assert lock.exists()
    assert sock.exists()


def test_stale_x11_lock_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / ".X99-lock"
    sock = tmp_path / "X99"
    lock.write_text("4242", encoding="utf-8")
    sock.touch()

    def gone(_pid: int, _signal: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", gone)
    BrowserRunner._clear_stale_x11_state(lock, sock)
    assert not lock.exists()
    assert not sock.exists()
