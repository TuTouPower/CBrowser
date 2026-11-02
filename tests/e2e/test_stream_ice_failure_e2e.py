"""Failed ICE preparation must preserve the active connection and its resources."""

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest


def _run_probe(fixture_name: str, use_mux: bool, cancel: bool = False) -> dict:
    image = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    if not image:
        pytest.skip("NOT_RUN: provide an immutable Stream Runtime image")
    assert image.startswith("sha256:"), "Use the built image ID, not a mutable tag"
    probe = (
        Path(__file__).resolve().parents[1] / "fixtures" / "stream_probe" / fixture_name
    )
    name = f"cbrowser-t004-ice-failure-{uuid.uuid4().hex[:12]}"
    args = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--label",
        "cbrowser.task=t004",
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
    if use_mux:
        args.append("--mux")
    if cancel:
        args.append("--cancel")
    try:
        result = subprocess.run(
            args, text=True, capture_output=True, timeout=40, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(result.stdout.strip().splitlines()[-1])
        return proof
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            check=False,
            capture_output=True,
            timeout=10,
        )


@pytest.mark.parametrize("use_mux", [False, True])
def test_failed_ice_restart_preserves_live_generation(use_mux: bool) -> None:
    proof = _run_probe("ice_restart_failure.py", use_mux)
    assert proof["three_restarts_rejected"]
    assert proof["old_channel_still_delivers"]
    assert proof["healthy_restart_after_failures"]
    assert proof["socket_count_after"] <= proof["socket_count_before"]
    assert proof["monitor_preserved"]
    assert proof["committed_generation"] == 2
    assert proof["mux"] is use_mux


@pytest.mark.parametrize("use_mux", [False, True])
def test_close_during_ice_restart_releases_both_generations(use_mux: bool) -> None:
    proof = _run_probe("ice_pending_close.py", use_mux)
    assert proof["active_closed"]
    assert proof["pending_closed"]
    assert proof["socket_count_after"] <= proof["socket_count_before"]
    assert proof["mux"] is use_mux


@pytest.mark.parametrize("use_mux", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
def test_unresponsive_turn_releases_provisional_sockets(
    use_mux: bool, cancel: bool
) -> None:
    proof = _run_probe("ice_turn_timeout.py", use_mux, cancel)
    assert proof["restarts_rejected"]
    assert proof["monitor_preserved"]
    assert proof["old_channel_still_delivers"]
    assert proof["socket_count_after"] <= proof["socket_count_before"]
    assert proof["mux"] is use_mux
    assert proof["cancelled"] is cancel
