"""Actual TURN rotations on fixed Selkies PeerConnection and DTLS transports."""

import json
import os
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import pytest


def test_three_relay_generations_preserve_live_peer(tmp_path: Path) -> None:
    stream_image = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    turn_image = os.environ.get("CBROWSER_TURN_TEST_IMAGE")
    if not stream_image or not turn_image:
        pytest.skip("NOT_RUN: provide immutable Stream and coturn test images")
    assert stream_image.startswith("sha256:") and turn_image.startswith("sha256:")
    os.chmod(tmp_path, 0o700)
    secret = secrets.token_hex(32)
    secret_file = tmp_path / "turn_secret"
    secret_file.write_text(secret)
    secret_file.chmod(0o644)
    config = tmp_path / "turnserver.conf"
    config.write_text(
        "listening-port=3478\nmin-port=41000\nmax-port=41040\n"
        "realm=cbrowser-ice-test\nuse-auth-secret\n"
        f"static-auth-secret={secret}\n"
        "no-cli\nno-tls\nno-dtls\npidfile=/tmp/turn.pid\n"
        "log-file=stdout\nsimple-log\n"
    )
    config.chmod(0o644)
    probe = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "stream_probe"
        / "ice_relay_generations.py"
    )
    name = "cbrowser-t004-relay-test-" + uuid.uuid4().hex[:12]
    network, turn, peer = name + "-net", name + "-turn", name + "-peer"
    network_created = False
    turn_id = None
    try:
        subprocess.run(
            ["docker", "network", "create", "--internal", network],
            text=True,
            capture_output=True,
            check=True,
            timeout=20,
        )
        network_created = True
        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                turn,
                "--network",
                network,
                "--network-alias",
                "turn",
                "--label",
                "cbrowser.task=t004",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "NET_BIND_SERVICE",
                "--security-opt",
                "no-new-privileges:true",
                "--tmpfs",
                "/tmp:rw,mode=1777",
                "-v",
                f"{config}:/etc/turnserver.conf:ro",
                "--entrypoint",
                "/usr/bin/turnserver",
                turn_image,
                "-c",
                "/etc/turnserver.conf",
                "--relay-threads=1",
            ],
            text=True,
            capture_output=True,
            check=True,
            timeout=20,
        )
        turn_id = result.stdout.strip()
        deadline = time.monotonic() + 5
        while True:
            sockets = subprocess.run(
                ["docker", "exec", turn_id, "cat", "/proc/net/udp"],
                text=True,
                capture_output=True,
                timeout=2,
                check=False,
            )
            if ":0D96 " in sockets.stdout:
                break
            assert time.monotonic() < deadline, "coturn UDP listener did not start"
            time.sleep(0.05)
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                peer,
                "--network",
                network,
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
                f"{secret_file}:/turn_secret:ro",
                "-v",
                f"{probe}:/probe.py:ro",
                "--entrypoint",
                "python3",
                stream_image,
                "/probe.py",
            ],
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )
        (tmp_path / "peer.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(result.stdout.strip().splitlines()[-1])
        assert proof["uid"] == 1000
        assert [row["generation"] for row in proof["relay_generations"]] == [2, 3, 4]
        for row in proof["relay_generations"]:
            assert row["server_candidate"] == row["client_candidate"] == "relay"
            assert row["old_send_rejected"] and row["same_dtls"]
            assert row["same_datachannel"] and row["mux_preserved"]
    finally:
        if turn_id:
            logs = subprocess.run(
                ["docker", "logs", turn_id],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            log_file = tmp_path / "turn.log"
            log_file.write_text(logs.stdout + logs.stderr)
            log_file.chmod(0o600)
        for container in [peer, turn_id]:
            if container:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
        if network_created:
            subprocess.run(
                ["docker", "network", "rm", network],
                capture_output=True,
                timeout=10,
                check=False,
            )
