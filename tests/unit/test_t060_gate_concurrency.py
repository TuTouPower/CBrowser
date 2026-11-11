"""Real process/file-lock and Docker ownership regressions."""

from __future__ import annotations

import fcntl
import subprocess
import sys
from pathlib import Path

from scripts import gate_container_cleanup as cleanup


def test_cleanup_preserves_running_and_unknown_runs(tmp_path):
    lease = tmp_path / ("a" * 32 + ".lock")
    lease.touch()
    (tmp_path / ("b" * 32 + ".lock")).touch()
    with lease.open("r+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX)
        plan = cleanup.select_cleanup_targets(
            ["active", "ended", "unowned"],
            ["active-net", "ended-net", "foreign-net"],
            container_labels={
                "active": {"com.cbrowser.gate-run": "a" * 32},
                "ended": {"com.cbrowser.gate-run": "b" * 32},
            },
            network_labels={
                "active-net": {"com.cbrowser.gate-run": "a" * 32},
                "ended-net": {"com.cbrowser.gate-run": "b" * 32},
            },
            runs_dir=tmp_path,
        )
        assert plan.containers == frozenset({"ended"})
        assert plan.networks == frozenset({"ended-net"})


def test_shared_venv_readers_block_rebuild(tmp_path):
    from scripts.gate_run import gate_environment

    root = Path(__file__).resolve().parents[2]
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "bin").mkdir()
    (venv / "bin/python").symlink_to(sys.executable)
    import hashlib

    stamp = venv / ".requirements.sha256"
    stamp.write_text(
        hashlib.sha256(
            (root / "scripts/gate-requirements.txt").read_bytes()
        ).hexdigest()
    )
    # A second process requests the same venv while a suite holds its shared
    # lease. Both warm readers must proceed, without invoking uv --clear.
    with gate_environment(root, venv):
        code = 'from pathlib import Path; from scripts.gate_run import gate_environment; import sys;\nwith gate_environment(Path(sys.argv[1]), Path(sys.argv[2])): print("reader-ready", flush=True)'
        result = subprocess.run(
            [sys.executable, "-c", code, str(root), str(venv)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "reader-ready" in result.stdout
        assert (venv / "bin/python").exists()


def test_stale_venv_rebuild_waits_for_running_gate(tmp_path):
    import hashlib

    import pytest

    from scripts.gate_run import gate_environment

    root = Path(__file__).resolve().parents[2]
    fake_root = tmp_path / "repo"
    (fake_root / "scripts").mkdir(parents=True)
    requirements = fake_root / "scripts/gate-requirements.txt"
    requirements.write_text("old")
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/python").symlink_to(sys.executable)
    (venv / ".requirements.sha256").write_text(hashlib.sha256(b"old").hexdigest())
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    uv = stub_bin / "uv"
    built = tmp_path / "rebuilt"
    uv.write_text(
        f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(built)!r}).touch()\n"
    )
    uv.chmod(0o755)
    import os

    env = {**os.environ, "PATH": str(stub_bin) + os.pathsep + os.environ["PATH"]}
    code = (
        "from pathlib import Path; from scripts.gate_run import gate_environment; import sys; "
        'print("requested",flush=True);\nwith gate_environment(Path(sys.argv[1]),Path(sys.argv[2])): print("rebuilt",flush=True)'
    )
    with gate_environment(fake_root, venv):
        requirements.write_text("new")
        child = subprocess.Popen(
            [sys.executable, "-c", code, str(fake_root), str(venv)],
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert child.stdout.readline().strip() == "requested"
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                child.communicate(timeout=0.2)
            assert not built.exists()
        except BaseException:
            child.kill()
            child.wait()
            raise
    stdout, stderr = child.communicate(timeout=10)
    assert child.returncode == 0, stderr
    assert "rebuilt" in stdout and built.is_file()
    assert (venv / ".requirements.sha256").read_text() == hashlib.sha256(
        b"new"
    ).hexdigest()


def test_same_checkout_excludes_generated_artifact_writers(tmp_path):
    import pytest

    from scripts.gate_run import checkout_lease

    root = Path(__file__).resolve().parents[2]
    code = (
        "from pathlib import Path; from scripts.gate_run import checkout_lease; import sys; "
        'print("requested",flush=True);\nwith checkout_lease(Path(sys.argv[1])): print("entered",flush=True)'
    )
    with checkout_lease(tmp_path):
        child = subprocess.Popen(
            [sys.executable, "-c", code, str(tmp_path)],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert child.stdout.readline().strip() == "requested"
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                child.communicate(timeout=0.2)
        except BaseException:
            child.kill()
            child.wait()
            raise
    stdout, stderr = child.communicate(timeout=10)
    assert child.returncode == 0, stderr
    assert "entered" in stdout
