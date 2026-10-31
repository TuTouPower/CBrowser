"""The Agent may confirm an ICE restart to Gateway only after real takeover."""

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest


def test_restart_commit_wait_reports_real_ice_outcome() -> None:
    image = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    if not image:
        pytest.skip("NOT_RUN: provide an immutable Stream Runtime image")
    assert image.startswith("sha256:"), "Use the built image ID, not a mutable tag"
    probe = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "stream_probe"
        / "ice_commit_outcome.py"
    )
    name = f"cbrowser-t006-ice-commit-{uuid.uuid4().hex[:12]}"
    args = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--label",
        "cbrowser.task=t006",
        "--user",
        "1000:1000",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,exec,mode=1777",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-v",
        f"{probe}:/probe.py:ro",
        "--entrypoint",
        "python3",
        image,
        "/probe.py",
    ]
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(result.stdout.strip().splitlines()[-1])
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name], check=False, capture_output=True, timeout=10
        )
    assert proof["healthy_committed"] == 2
    assert proof["healthy_pending"] is False
    assert proof["healthy_delivers"] is True
    assert proof["failed_error"] == "ConnectionError"
    assert proof["failed_target_generation"] == 3
    assert proof["failed_committed_generation"] == 2
