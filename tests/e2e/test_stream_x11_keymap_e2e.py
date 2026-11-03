"""Real Xvfb/Stream images must preserve native text bindings across reuse."""

import json
import subprocess
import uuid
from pathlib import Path


from e2e_env import require_e2e_env
from wait import wait_until_sync


def test_native_keymap_reuse_preserves_every_binding(tmp_path: Path) -> None:
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE", "CBROWSER_STREAM_TEST_IMAGE"
    )
    browser_image = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_image = env["CBROWSER_STREAM_TEST_IMAGE"]
    assert browser_image.startswith("sha256:") and stream_image.startswith("sha256:")
    socket_dir = tmp_path / "x11"
    socket_dir.mkdir(mode=0o777)
    socket_dir.chmod(0o777)
    name = "cbrowser-t004-xkb-test-" + uuid.uuid4().hex[:12]
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures/stream_probe/x11_keymap_probe.py"
    )
    created = False
    try:
        # This diagnostic X server has no browser or profile data. Its socket
        # exists only in this test's private directory and is never published.
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--tmpfs",
                "/tmp:rw,mode=1777",
                "-v",
                f"{socket_dir}:/tmp/.X11-unix",
                "--entrypoint",
                "Xvfb",
                browser_image,
                ":99",
                "-screen",
                "0",
                "1920x1080x24",
                "-ac",
                "-nolisten",
                "tcp",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        created = True
        wait_until_sync(
            lambda: (socket_dir / "X99").is_socket(),
            timeout=5.0,
            description="diagnostic Xvfb socket",
        )
        assert (socket_dir / "X99").is_socket(), "Diagnostic Xvfb did not start"
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--user",
                "1000:1000",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--tmpfs",
                "/tmp:rw,mode=1777",
                "-v",
                f"{socket_dir / 'X99'}:/tmp/.X11-unix/X99:ro",
                "-v",
                f"{fixture}:/probe.py:ro",
                "-e",
                "DISPLAY=:99",
                "--entrypoint",
                "python3",
                stream_image,
                "/probe.py",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        proof = json.loads(result.stdout.strip().splitlines()[-1])
        assert proof["idempotent"] and len(proof["rounds"]) == 5
        assert proof["held_slots_unchanged"]
    finally:
        if created:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True,
                timeout=10,
                check=False,
            )
