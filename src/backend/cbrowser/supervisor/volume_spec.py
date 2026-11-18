"""Typed Docker volume mount specifications for supervisor containers.

t080 / ADR 029: every mount is a named-volume subpath mount built by
:class:`~cbrowser.supervisor.storage_layout.MountPlanner`.  No host bind
mounts remain for runtime data; a source outside the managed storage
roots fails closed at construction time.
"""

from __future__ import annotations

from pathlib import Path

from docker.types import Mount

from cbrowser.supervisor.storage_layout import MountPlanner

SINGLETON_LOCK_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")

PREVIEW_CONTAINER_DIR = "/data/preview"


def browser_volumes(
    *,
    planner: MountPlanner,
    profile_id: str,
    dirs: dict[str, Path],
    gate: Path,
    engine_cache: Path,
    geoip_cache: Path,
    credentials_path: Path | None = None,
) -> list[Mount]:
    upload_dir = dirs.get("uploads") or dirs["exchange"].parent / "uploads"
    preview_dir = dirs.get("preview") or dirs["profile"].parent / "preview"
    items: list[tuple[Path, str, str]] = [
        (gate, "/run/cbrowser_policy", "ro"),
        (dirs["profile"], f"/data/profiles/{profile_id}/profile", "rw"),
        (dirs["events"], f"/data/runtime-events/{profile_id}", "rw"),
        (dirs["exchange"], "/exchange/downloads", "rw"),
        (upload_dir, "/exchange/uploads", "rw"),
        (dirs["runtime"], "/run/cbrowser/runtime", "rw"),
        (dirs["x11"], "/tmp/.X11-unix", "rw"),
        (dirs["pulse"], "/pulse", "rw"),
        (preview_dir, PREVIEW_CONTAINER_DIR, "rw"),
        (engine_cache, "/data/engine-cache", "ro"),
        (geoip_cache, "/data/engine-cache/geoip", "ro"),
    ]
    if credentials_path is not None:
        items.append(
            (credentials_path, "/run/cbrowser/proxy_credentials.json", "ro")
        )
    return planner.mounts_for(items)


def stream_volumes(
    *,
    planner: MountPlanner,
    gate: Path,
    x11_socket: Path,
    xauth_file: Path,
    pulse_dir: Path,
    secret_file: Path,
    selkies_file: Path,
) -> list[Mount]:
    items: list[tuple[Path, str, str]] = [
        (gate, "/run/cbrowser_policy", "ro"),
        (x11_socket, "/tmp/.X11-unix/X99", "ro"),
        (xauth_file, "/tmp/.Xauthority", "ro"),
        (pulse_dir, "/pulse", "ro"),
        (secret_file, "/tmp/secret.txt", "ro"),
        (selkies_file, "/tmp/selkies_credentials.json", "ro"),
    ]
    return planner.mounts_for(items)


def cache_init_volumes(
    *, planner: MountPlanner, engine_cache: Path, geoip_cache: Path
) -> list[Mount]:
    items: list[tuple[Path, str, str]] = [
        (engine_cache, "/data/engine-cache", "rw"),
        (geoip_cache, "/data/engine-cache/geoip", "rw"),
    ]
    return planner.mounts_for(items)
