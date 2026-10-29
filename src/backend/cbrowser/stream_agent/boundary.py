"""
Audio and display boundary verification for Stream Runtime.
Ensures PulseAudio and X11 access without touching browser
profile data or Docker socket.
"""

from pathlib import Path
from typing import Any, Dict


class SecurityError(RuntimeError):
    """Raised when runtime isolation boundary invariants are violated."""

    pass


PROHIBITED_PATHS = (
    "/var/run/docker.sock",
    "/run/docker.sock",
    "/data/profiles",
    "/home/cbrowser/.config",
    "/root/.config/google-chrome",
    "/run/cbrowser/runtime/agent.sock",
    "/tmp/cbrowser-agent.sock",
    "/run/cbrowser/runtime/userdata",
    "/run/cbrowser/runtime/events",
    "/data/cbrowser.db",
    "/app/data/cbrowser.db",
)


def verify_stream_runtime_boundaries(
    pulse_dir: str = "/pulse",
    x11_socket: str = "/tmp/.X11-unix/X99",
    xauthority_path: str = "/tmp/.Xauthority",
) -> Dict[str, Any]:
    """
    Verifies that Stream Runtime has access only to its authorized endpoints:
    - X11 socket and Xauthority
    - PulseAudio socket and cookie
    - NEVER Docker socket (/var/run/docker.sock)
    - NEVER browser user data directory (/data/profiles)
    - NEVER browser agent socket (/run/cbrowser/runtime/agent.sock)
    - NEVER sqlite databases or whole runtime mounts
    """
    results: Dict[str, Any] = {
        "x11_available": Path(x11_socket).exists(),
        "xauth_available": Path(xauthority_path).is_file(),
        "pulse_dir_available": Path(pulse_dir).is_dir(),
        "pulse_cookie_available": (Path(pulse_dir) / "pulse.cookie").is_file(),
        "docker_socket_exposed": Path("/var/run/docker.sock").exists()
        or Path("/run/docker.sock").exists(),
        "profile_userdata_exposed": Path("/data/profiles").exists(),
        "prohibited_paths_detected": [],
    }

    # Strict isolation assertions across declared prohibited danger paths
    for p in PROHIBITED_PATHS:
        try:
            path_obj = Path(p)
            if path_obj.exists():
                results["prohibited_paths_detected"].append(p)
                raise SecurityError(
                    "CRITICAL SECURITY VIOLATION: Prohibited path mounted "
                    f"into Stream Runtime: {p}"
                )
        except PermissionError:
            # If parent permissions forbid traversal (e.g. /root for UID 1000),
            # the path is not accessible to the unprivileged process.
            pass

    return results
