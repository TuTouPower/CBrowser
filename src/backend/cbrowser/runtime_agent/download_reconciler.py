"""Reconcile completed files in the download directory with CDP download events."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path

from .event_storage import EventStorage
from .protocol import DownloadEventRecord

logger = logging.getLogger("cbrowser.runtime_agent.download_reconciler")

TEMP_SUFFIXES = (".crdownload", ".part", ".partial", ".download", ".tmp")
CHUNK_SIZE = 1024 * 1024
# Browser.setDownloadBehavior("allowAndName") stores the file under the
# internal CDP guid. That guid is never a legitimate artifact name.
_CDP_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _is_temporary(name: str) -> bool:
    lowered = name.lower()
    return name.startswith((".incoming-", ".tmp-")) or lowered.endswith(TEMP_SUFFIXES)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def installed_download_keys(storage: EventStorage) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    try:
        events = storage.get_download_events()
    except Exception:  # noqa: BLE001 - corrupt history must not block a fresh scan
        return keys
    for event in events:
        if event.state == "completed" and event.download_path and event.sha256:
            keys.add((str(Path(event.download_path)), event.sha256))
    return keys


async def scan_completed_downloads(
    download_dir: Path | str,
    profile_id: str,
    runtime_instance_id: str,
    storage: EventStorage,
    *,
    existing_keys: set[tuple[str, str]] | None = None,
    skip_paths: set[str] | None = None,
) -> list[DownloadEventRecord]:
    """Emit completed events for files lacking a matching path+checksum event.

    ``skip_paths`` holds files still tracked by an in-flight CDP download:
    their real name comes from ``downloadWillBegin`` and a scan event would
    race the CDP completion event (t035 t008 regression).
    """
    directory = Path(download_dir)
    if not directory.is_dir():
        return []
    seen = (
        existing_keys if existing_keys is not None else installed_download_keys(storage)
    )
    skipped = {str(Path(path).resolve()) for path in (skip_paths or ())}
    created: list[DownloadEventRecord] = []
    for item in sorted(directory.iterdir()):
        if not item.is_file() or item.is_symlink() or _is_temporary(item.name):
            continue
        resolved = str(item.resolve())
        if resolved in skipped:
            continue
        try:
            digest = await asyncio.to_thread(_sha256_file, item)
            size = item.stat().st_size
        except OSError:
            continue
        key = (resolved, digest)
        if key in seen:
            continue
        seen.add(key)
        event = DownloadEventRecord(
            event_id=(
                "dl_scan_"
                + hashlib.sha256(f"{resolved}:{digest}".encode()).hexdigest()[:32]
            ),
            profile_id=profile_id,
            runtime_instance_id=runtime_instance_id,
            guid=f"scan-{digest[:16]}",
            suggested_filename=(
                None if _CDP_GUID_RE.fullmatch(item.name) else item.name
            ),
            download_path=resolved,
            state="completed",
            received_bytes=size,
            total_bytes=size,
            size_bytes=size,
            sha256=digest,
        )
        storage.save_download_event(event)
        created.append(event)
        logger.info("Reconciled completed download: %s", item.name)
    return created
