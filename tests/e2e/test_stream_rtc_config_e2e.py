"""Gateway stream-side TURN config must reach Selkies RTCApp for new peers."""

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest


def test_gateway_rtc_config_reaches_selkies_rtc_app() -> None:
    image = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    if not image:
        pytest.skip("NOT_RUN: provide an immutable Stream Runtime image")
    assert image.startswith("sha256:"), "Use the built image ID, not a mutable tag"
    probe = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "stream_probe"
        / "rtc_config_apply.py"
    )
    name = f"cbrowser-t006-rtc-config-{uuid.uuid4().hex[:12]}"
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
        result = subprocess.run(
            args, text=True, capture_output=True, timeout=60, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(result.stdout.strip().splitlines()[-1])
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name], check=False, capture_output=True, timeout=10
        )
    expected = [
        {
            "urls": f"turn:10.0.0.5:3478?transport={transport}",
            "username": "1793000000:stream-profile_rtc_apply",
            "credential": "c3RyZWFtLXNpZGUvY3JlZD0=",
        }
        for transport in ("udp", "tcp")
    ]
    assert proof["before_ready"] == []
    assert proof["after_ready"] == expected
    assert [s["username"] for s in proof["after_rotation"]] == [
        "1793043200:stream-profile_rtc_apply"
    ] * 2


def test_gateway_rtc_config_relay_only_restricts_candidates() -> None:
    image = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    if not image:
        pytest.skip("NOT_RUN: provide an immutable Stream Runtime image")
    assert image.startswith("sha256:"), "Use the built image ID, not a mutable tag"
    probe = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "stream_probe"
        / "rtc_config_relay_only.py"
    )
    name = f"cbrowser-t006-relay-probe-{uuid.uuid4().hex[:12]}"
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
        result = subprocess.run(
            args, text=True, capture_output=True, timeout=60, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(result.stdout.strip().splitlines()[-1])
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name], check=False, capture_output=True, timeout=10
        )

    assert "host" in proof["normal_cands"]
    assert proof["relay_failed_closed"] is True
    assert proof["filtered_cands"] == ["relay"]
