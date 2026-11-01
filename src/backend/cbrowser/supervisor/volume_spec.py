"""Stateless Docker volume mount specifications for supervisor containers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SINGLETON_LOCK_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def browser_volumes(
    *,
    profile_id: str,
    dirs: dict[str, Path],
    gate: Path,
    engine_cache: Path,
    geoip_cache: Path,
) -> dict[str, dict[str, Any]]:
    return {
        str(gate): {"bind": "/run/cbrowser_policy", "mode": "ro"},
        str(dirs["profile"]): {
            "bind": f"/data/profiles/{profile_id}/profile",
            "mode": "rw",
        },
        str(dirs["events"]): {
            "bind": f"/data/runtime-events/{profile_id}",
            "mode": "rw",
        },
        str(dirs["exchange"]): {"bind": "/exchange/downloads", "mode": "rw"},
        str(dirs["runtime"]): {"bind": "/run/cbrowser/runtime", "mode": "rw"},
        str(dirs["x11"]): {"bind": "/tmp/.X11-unix", "mode": "rw"},
        str(dirs["pulse"]): {"bind": "/pulse", "mode": "rw"},
        str(engine_cache): {"bind": "/data/engine-cache", "mode": "ro"},
        str(geoip_cache): {
            "bind": "/data/engine-cache/geoip",
            "mode": "ro",
        },
    }


def stream_volumes(
    *,
    gate: Path,
    x11_socket: Path,
    xauth_file: Path,
    pulse_dir: Path,
    secret_file: Path,
    selkies_file: Path,
) -> dict[str, dict[str, str]]:
    return {
        str(gate): {"bind": "/run/cbrowser_policy", "mode": "ro"},
        str(x11_socket): {"bind": "/tmp/.X11-unix/X99", "mode": "ro"},
        str(xauth_file): {"bind": "/tmp/.Xauthority", "mode": "ro"},
        str(pulse_dir): {"bind": "/pulse", "mode": "ro"},
        str(secret_file): {"bind": "/tmp/secret.txt", "mode": "ro"},
        str(selkies_file): {
            "bind": "/tmp/selkies_credentials.json",
            "mode": "ro",
        },
    }


def cache_init_volumes(
    *, engine_cache: Path, geoip_cache: Path
) -> dict[str, dict[str, str]]:
    return {
        str(engine_cache): {
            "bind": "/data/engine-cache",
            "mode": "rw",
        },
        str(geoip_cache): {
            "bind": "/data/engine-cache/geoip",
            "mode": "rw",
        },
    }
