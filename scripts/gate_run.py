"""Own the gate venv and run leases across all suite subprocesses.

flock(2) is available on macOS through fcntl, without a flock CLI package.
A warm reader takes only a shared lock; rebuilders recheck under an exclusive
lock and atomically downgrade before launching the suites.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


@contextmanager
def gate_environment(root: Path, venv: Path):
    venv.parent.mkdir(parents=True, exist_ok=True)
    required = hashlib.sha256(
        (root / "scripts/gate-requirements.txt").read_bytes()
    ).hexdigest()
    stamp = venv / ".requirements.sha256"

    def ready():
        return (
            (venv / "bin/python").is_file()
            and stamp.is_file()
            and stamp.read_text() == required
        )

    with (venv.parent / (venv.name + ".lock")).open("a+") as lock:
        # Serialize the check/rebuild/install transaction, independently of
        # the runtime readers. A warm gate can join existing readers; a
        # stale environment waits for every running gate before rebuilding.
        with (venv.parent / (venv.name + ".prepare.lock")).open("a+") as prepare:
            fcntl.flock(prepare, fcntl.LOCK_EX)
            fcntl.flock(lock, fcntl.LOCK_SH)
            if not ready():
                fcntl.flock(lock, fcntl.LOCK_UN)
                fcntl.flock(lock, fcntl.LOCK_EX)
                subprocess.run(
                    [
                        "uv",
                        "venv",
                        "--clear",
                        "--python",
                        os.environ.get("GATE_PYTHON_MINOR", "3.15"),
                        str(venv),
                    ],
                    cwd=root,
                    check=True,
                )
                subprocess.run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--python",
                        str(venv / "bin/python"),
                        "-r",
                        "scripts/gate-requirements.txt",
                    ],
                    cwd=root,
                    check=True,
                )
                stamp.write_text(required)
                fcntl.flock(lock, fcntl.LOCK_SH)
        yield lock


@contextmanager
def checkout_lease(root: Path):
    """One gate owns a checkout's generated dist until its consumers finish.

    Different worktrees still share the venv concurrently; two processes
    in the same checkout cannot replace each other's build output.
    """
    directory = root / ".scratch"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "gate_checkout.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield lock


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    root = Path(__file__).resolve().parents[1]
    venv = Path(
        os.environ.get("CBROWSER_GATE_VENV", root / ".scratch/gate_venv")
    ).resolve()
    env = dict(os.environ)
    env.setdefault(
        "UV_CACHE_DIR",
        env.get("CBROWSER_GATE_UV_CACHE", str(root / ".scratch/gate_uv_cache")),
    )
    os.environ["UV_CACHE_DIR"] = env["UV_CACHE_DIR"]
    # The common Git directory joins worktrees without ever modifying their
    # branches or task state. Missing/foreign leases never authorize deletion.
    common = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=root, text=True
    ).strip()
    runs = (root / common / "gate_runs").resolve()
    runs.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    env.update(
        CBROWSER_GATE_ENV_READY="1",
        CBROWSER_GATE_RUN_ID=run_id,
        CBROWSER_GATE_RUNS_DIR=str(runs),
        CBROWSER_GATE_VENV=str(venv),
    )
    evidence = env.get("CBROWSER_GATE_EVIDENCE_DIR")
    if evidence:
        Path(evidence).mkdir(parents=True, exist_ok=True)
        # Bootstrap can fail before Bash initializes its suite evidence. Never
        # let a new run identity coexist with a previous successful manifest.
        (Path(evidence) / "manifest.json").unlink(missing_ok=True)
        (Path(evidence) / "run.json").write_text(
            json.dumps({"run_id": run_id, "pid": os.getpid()})
        )
    with (
        (runs / (run_id + ".lock")).open("a+") as lease,
        checkout_lease(root) as checkout,
        ExitStack() as environment_lease,
    ):
        fcntl.flock(lease, fcntl.LOCK_EX)
        try:
            lock = environment_lease.enter_context(gate_environment(root, venv))
        except (OSError, subprocess.CalledProcessError) as exc:
            logger.error("gate environment preparation failed (%s)", type(exc).__name__)
            if evidence:
                directory = Path(evidence)
                (directory / "logs").mkdir(exist_ok=True)
                # Do not copy arbitrary command output, paths or credentials
                # into evidence when the redaction environment is unavailable.
                (directory / "logs/environment.log").write_text(
                    f"environment preparation failed: {type(exc).__name__}; "
                    f"exit_code={getattr(exc, 'returncode', 1)}\n"
                )
                manifest = {
                    "run_id": run_id,
                    "suites": [{
                        "name": "environment", "command": "prepare gate environment",
                        "exit_code": 1, "status": "failed", "log": "logs/environment.log",
                    }],
                    "image_identity": {"error": "environment unavailable before identity collection"},
                    "all_passed": False,
                }
                temporary = directory / f".manifest.{run_id}.tmp"
                temporary.write_text(json.dumps(manifest, indent=2) + "\n")
                os.replace(temporary, directory / "manifest.json")
            return 1
        docker_bin = env.get("CBROWSER_GATE_DOCKER_BIN") or shutil.which("docker")
        if docker_bin:
            adapter_dir = Path(tempfile.mkdtemp(prefix="gate_docker_", dir=venv.parent))
            adapter = adapter_dir / "docker"
            adapter.write_text(
                f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(root / 'scripts/gate_docker.py')!r}, run_name='__main__')\n"
            )
            adapter.chmod(0o755)
            env["CBROWSER_GATE_DOCKER_BIN"] = docker_bin
            env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
            env["PATH"] = str(adapter_dir) + os.pathsep + env["PATH"]
        process = subprocess.Popen(
            ["bash", str(root / "scripts/run_gates.sh"), *sys.argv[1:]],
            cwd=root,
            env=env,
            pass_fds=(lease.fileno(), lock.fileno(), checkout.fileno()),
            start_new_session=True,
        )
        previous = {}
        def forward_signal(signum, _frame):
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, forward_signal)
        try:
            result = process.wait()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        lease.close()  # inherited leases keep orphaned suite processes protected
        cleanup = subprocess.run(
            [str(venv / "bin/python"), str(root / "scripts/gate_container_cleanup.py")],
            cwd=root,
            env=env,
            check=False,
        )
        if evidence and (Path(evidence) / "manifest.json").is_file():
            manifest_path = Path(evidence) / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["cleanup_exit_code"] = cleanup.returncode
            manifest["all_passed"] = manifest["all_passed"] and cleanup.returncode == 0
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        if docker_bin:
            shutil.rmtree(adapter_dir)
        return result if result else cleanup.returncode


if __name__ == "__main__":
    raise SystemExit(main())
