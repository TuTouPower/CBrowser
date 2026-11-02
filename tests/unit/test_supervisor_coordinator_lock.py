"""Use real processes to verify sole ownership and kernel crash recovery."""

import subprocess
import sys
import time

import pytest
from cbrowser.supervisor.coordinator_lock import CoordinatorLock


def test_only_one_process_can_coordinate_a_data_root(tmp_path):
    path = tmp_path / "supervisor.lock"
    with (
        CoordinatorLock(path),
        pytest.raises(RuntimeError, match="Another Supervisor"),
        CoordinatorLock(path),
    ):
        pytest.fail("second coordinator acquired an owned root")
    with CoordinatorLock(path):
        assert path.is_file()


def test_sigkill_releases_lock_without_deleting_lock_file(tmp_path):
    path = tmp_path / "supervisor.lock"
    ready = tmp_path / "ready"
    program = (
        "import signal,sys; from pathlib import Path; "
        "from cbrowser.supervisor.coordinator_lock import CoordinatorLock; "
        "lock=CoordinatorLock(Path(sys.argv[1])); lock.__enter__(); "
        "Path(sys.argv[2]).touch(); signal.pause()"
    )
    child = subprocess.Popen([sys.executable, "-c", program, str(path), str(ready)])
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            assert child.poll() is None
            time.sleep(0.02)
        assert ready.exists()
        with pytest.raises(RuntimeError, match="Another Supervisor"), CoordinatorLock(
            path
        ):
            pytest.fail("owned lock acquired")
        child.kill()
        child.wait(timeout=5)
        with CoordinatorLock(path):
            assert path.exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
