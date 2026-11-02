"""Forward Agent download completion events to the API Artifact Service."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from cbrowser.runtime_agent.protocol import DownloadEventRecord
from cbrowser.supervisor.file_storage import atomic_write_text
from pydantic import ValidationError

logger = logging.getLogger("cbrowser.supervisor.artifact_forwarder")

CONTAINER_DOWNLOAD_PREFIX = "/exchange/downloads/"
RETRYABLE_4XX = frozenset({401, 403, 408, 429})


def translate_download_path(
    raw_path: str, data_root: Path | str, profile_id: str
) -> str:
    if raw_path.startswith(CONTAINER_DOWNLOAD_PREFIX):
        relative = raw_path[len(CONTAINER_DOWNLOAD_PREFIX) :]
        return str(Path(data_root) / "artifacts" / profile_id / "downloads" / relative)
    return raw_path


class DownloadArtifactForwarder:
    """At-least-once delivery; API dedupes by path and SHA-256.

    Processed event IDs are persisted instead of a single mtime cursor. A
    cursor skips older completed events whenever a newer begin/cancel event
    is ordered before them, which can happen after an API outage.
    """

    def __init__(
        self,
        data_root: Path | str,
        api_client: httpx.AsyncClient,
        cursor_file: Path | str | None = None,
    ):
        self.data_root = Path(data_root)
        self.api_client = api_client
        self.events_root = self.data_root / "runtime-events"
        self.cursor_file = Path(
            cursor_file or self.data_root / "control" / "download_cursors.json"
        )
        self._processed = self._load_processed()

    def _load_processed(self) -> dict[str, dict[str, set[str]]]:
        if not self.cursor_file.is_file():
            return {}
        try:
            raw = json.loads(self.cursor_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return {}
        processed: dict[str, dict[str, set[str]]] = {}
        if not isinstance(raw, dict):
            return processed
        for profile_id, instances in raw.items():
            if not isinstance(instances, dict):
                continue
            for instance_id, event_ids in instances.items():
                if isinstance(event_ids, list) and all(
                    isinstance(event_id, str) for event_id in event_ids
                ):
                    processed.setdefault(str(profile_id), {})[str(instance_id)] = set(
                        event_ids
                    )
        return processed

    def _save_processed(self) -> None:
        serializable = {
            profile_id: {
                instance_id: sorted(event_ids)
                for instance_id, event_ids in instances.items()
            }
            for profile_id, instances in self._processed.items()
        }
        try:
            self.cursor_file.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(self.cursor_file, json.dumps(serializable), mode=0o600)
        except OSError as exc:
            logger.warning(
                "Download forwarder state persistence failed: error_type=%s",
                type(exc).__name__,
            )

    def _is_processed(self, profile_id: str, instance_id: str, key: str) -> bool:
        return key in self._processed.get(profile_id, {}).get(instance_id, set())

    def _mark_processed(self, profile_id: str, instance_id: str, key: str) -> None:
        self._processed.setdefault(profile_id, {}).setdefault(instance_id, set()).add(
            key
        )

    async def forward_pending(self) -> int:
        if not self.events_root.is_dir():
            return 0
        forwarded = 0
        changed = False
        present: dict[tuple[str, str], set[str]] = {}
        for profile_dir in sorted(self.events_root.iterdir()):
            if not profile_dir.is_dir():
                continue
            profile_id = profile_dir.name
            events_dir = profile_dir / "events" / "downloads"
            if not events_dir.is_dir():
                continue
            for event_file in sorted(events_dir.glob("*.json")):
                try:
                    event_file.resolve().relative_to(self.events_root.resolve())
                except ValueError:
                    continue
                event: DownloadEventRecord | None = None
                try:
                    data = json.loads(event_file.read_text(encoding="utf-8"))
                    event = DownloadEventRecord.model_validate(data)
                except (OSError, ValueError, ValidationError, UnicodeError):
                    instance_id = "_invalid"
                    key = f"unparsed:{event_file.name}"
                else:
                    instance_id = event.runtime_instance_id
                    key = event.event_id
                present.setdefault((profile_id, instance_id), set()).add(key)
                if self._is_processed(profile_id, instance_id, key):
                    continue
                if event is None:
                    self._mark_processed(profile_id, instance_id, key)
                    changed = True
                    continue
                if event.state != "completed" or not event.download_path:
                    self._mark_processed(profile_id, instance_id, key)
                    changed = True
                    continue
                payload = {
                    "event_id": event.event_id,
                    "profile_id": event.profile_id,
                    "runtime_instance_id": event.runtime_instance_id,
                    "path": translate_download_path(
                        event.download_path, self.data_root, event.profile_id
                    ),
                    "name": (
                        event.suggested_filename or Path(event.download_path).name
                    )[:255],
                    "size": event.size_bytes or event.received_bytes,
                    "sha256": event.sha256,
                    "content_type": None,
                }
                try:
                    response = await self.api_client.post(
                        "/api/v1/internal/supervisor/artifacts/downloads",
                        json=payload,
                    )
                except httpx.HTTPError:
                    if changed:
                        self._save_processed()
                    return forwarded
                if response.status_code == 200:
                    forwarded += 1
                    self._mark_processed(profile_id, instance_id, key)
                    changed = True
                elif 400 <= response.status_code < 500:
                    if response.status_code in RETRYABLE_4XX:
                        if changed:
                            self._save_processed()
                        return forwarded
                    logger.warning(
                        "Download event rejected: profile=%s status=%s",
                        profile_id,
                        response.status_code,
                    )
                    self._mark_processed(profile_id, instance_id, key)
                    changed = True
                else:
                    if changed:
                        self._save_processed()
                    return forwarded
        if changed:
            self._prune(present)
            self._save_processed()
        return forwarded

    def _prune(self, present: dict[tuple[str, str], set[str]]) -> None:
        for (profile_id, instance_id), keys in present.items():
            existing = self._processed.get(profile_id, {}).get(instance_id)
            if existing is not None:
                existing.intersection_update(keys)
