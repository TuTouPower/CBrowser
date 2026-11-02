"""Subsystem health and readiness validation for Browser Runtime."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.request
from pathlib import Path

logger = logging.getLogger("cbrowser.runtime_agent.subsystems")


def check_display(
    display: str, xauth_path: Path | str | None = None
) -> tuple[bool, str]:
    """Verify that X11 display server and socket are alive and accessible."""
    display_num = display.lstrip(":")
    socket_path = Path(f"/tmp/.X11-unix/X{display_num}")
    if not socket_path.exists():
        return False, f"X11 socket not found at {socket_path}"

    env = dict(os.environ)
    env["DISPLAY"] = display
    if xauth_path:
        env["XAUTHORITY"] = str(xauth_path)

    # Probe with xdpyinfo - must be installed in container (fail-closed)
    try:
        proc = subprocess.run(
            ["xdpyinfo"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=1.5,
            check=False,
        )
        if proc.returncode == 0:
            return True, "xdpyinfo succeeded"
        # If xdpyinfo returns non-zero, auth or connection failed
        err = proc.stderr.decode().strip()
        return False, f"xdpyinfo failed with code {proc.returncode}: {err}"
    except FileNotFoundError:
        return (
            False,
            "xdpyinfo tool missing; cannot verify X11 display readiness (fail-closed)",
        )
    except Exception as e:  # noqa: BLE001 - unexpected X11 probe exception returns failure tuple
        return False, f"X11 probe error: {e}"


def check_audio(pulse_sock: Path | str, pulse_cookie: Path | str) -> tuple[bool, str]:
    """Verify PulseAudio virtual sink and cookie authentication."""
    sock = Path(pulse_sock)
    cookie = Path(pulse_cookie)

    if not sock.exists():
        return False, f"PulseAudio socket not found at {sock}"
    if not cookie.exists():
        return False, f"PulseAudio cookie not found at {cookie}"
    if cookie.stat().st_size != 256:
        return (
            False,
            f"Invalid PulseAudio cookie size: {cookie.stat().st_size} bytes",
        )

    env = dict(os.environ)
    env["PULSE_SERVER"] = f"unix:{sock}"
    env["PULSE_COOKIE"] = str(cookie)

    try:
        # Check pactl info
        proc_info = subprocess.run(
            ["pactl", "info"],
            env=env,
            capture_output=True,
            timeout=1.5,
            check=False,
        )
        if proc_info.returncode != 0:
            err = proc_info.stderr.decode().strip()
            return False, f"pactl info failed with code {proc_info.returncode}: {err}"

        # Check virtual sink existence and sample rate 48000Hz
        proc_sinks = subprocess.run(
            ["pactl", "list", "sinks"],
            env=env,
            capture_output=True,
            timeout=1.5,
            check=False,
        )
        if proc_sinks.returncode != 0:
            err = proc_sinks.stderr.decode().strip()
            return False, f"pactl list sinks failed: {err}"

        out_sinks = proc_sinks.stdout.decode()
        if "cbrowser_sink" not in out_sinks and "Sink #" not in out_sinks:
            return False, "PulseAudio virtual sink not found"

        if "48000 Hz" not in out_sinks and "48000" not in out_sinks:
            return False, "PulseAudio sink rate 48000Hz not verified"

        # Check sink state: IDLE, RUNNING, or SUSPENDED are all valid operational states
        # but ERROR or unexpected failure states are not
        has_valid_state = any(
            state in out_sinks
            for state in (
                "State: IDLE",
                "State: RUNNING",
                "State: SUSPENDED",
                "IDLE",
                "RUNNING",
                "SUSPENDED",
            )
        )
        if not has_valid_state:
            return (
                False,
                "PulseAudio sink not in operational state (IDLE/RUNNING/SUSPENDED)",
            )

        return True, "PulseAudio connection and 48000Hz sink verified"
    except FileNotFoundError:
        return (
            False,
            "pactl tool missing; cannot verify PulseAudio virtual sink (fail-closed)",
        )
    except Exception as e:  # noqa: BLE001 - unexpected pactl probe exception returns failure tuple
        return False, f"PulseAudio probe error: {e}"


def check_browser(cdp_port: int, browser_pid: int | None = None) -> tuple[bool, str]:
    """Verify that Chrome process is running and CDP endpoint responds."""
    if browser_pid is not None:
        try:
            os.kill(browser_pid, 0)
        except OSError:
            return False, f"Browser process PID {browser_pid} is not running"

    if cdp_port <= 0:
        return False, "Invalid or uninitialized CDP port"

    url = f"http://127.0.0.1:{cdp_port}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            if resp.status != 200:
                return False, f"CDP HTTP endpoint returned status {resp.status}"
            data = json.loads(resp.read().decode())
            if "Browser" not in data:
                return False, "CDP response missing 'Browser' metadata"
            return True, f"CDP active: {data.get('Browser')}"
    except Exception as e:  # noqa: BLE001 - unexpected CDP probe exception returns failure tuple
        return False, f"Failed to reach CDP HTTP endpoint {url}: {e}"
