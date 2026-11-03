"""Forward Agent download completion events to the API Artifact Service."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
from cbrowser.runtime_agent.protocol import DownloadEventRecord
from cbrowser.supervisor.event_forwarder import RETRYABLE_4XX
from cbrowser.supervisor.file_storage import atomic_write_text
from cbrowser.supervisor.path_validator import PathSecurityError, validate_profile_id
from pydantic import ValidationError

logger = logging.getLogger("cbrowser.supervisor.artifact_forwarder")

CONTAINER_DOWNLOAD_PREFIX = "/exchange/downloads/"
DOWNLOAD_EVENT_ENVELOPE_VERSION = 1


def translate_download_path(
    raw_path: str, data_root: Path | str, profile_id: str
) -> str:
    try:
        validate_profile_id(profile_id)
    except PathSecurityError:
        raise ValueError("Invalid download profile identity") from None
    downloads_root = (
        Path(data_root) / "artifacts" / profile_id / "downloads"
    ).resolve()
    if raw_path.startswith(CONTAINER_DOWNLOAD_PREFIX):
        relative = raw_path[len(CONTAINER_DOWNLOAD_PREFIX) :]
        candidate = downloads_root / relative
    else:
        candidate = Path(raw_path)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(downloads_root):
        raise ValueError("Download path escapes the Profile download directory")
    return str(resolved)


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

    @staticmethod
    def _parse_event(data: Any) -> tuple[DownloadEventRecord | None, str]:
        if not isinstance(data, dict):
            return None, "invalid_event"
        version = data.get("version", DOWNLOAD_EVENT_ENVELOPE_VERSION)
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version != DOWNLOAD_EVENT_ENVELOPE_VERSION
        ):
            return None, "unsupported_version"
        body = {key: value for key, value in data.items() if key != "version"}
        try:
            return DownloadEventRecord.model_validate(body), ""
        except ValidationError:
            return None, "invalid_event"

    def _dead_letter(self, event_file: Path, profile_id: str, reason: str) -> None:
        target_dir = self.data_root / "control" / "download-dead-letter" / profile_id
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / (
                f"{event_file.stem}.{reason}.{uuid.uuid4().hex}.json"
            )
            os.replace(event_file, target)
        except OSError as exc:
            logger.warning(
                "Download event dead-letter failed: profile=%s reason=%s "
                "error_type=%s",
                profile_id,
                reason,
                type(exc).__name__,
            )
            return
        logger.warning(
            "Download event moved to dead-letter: profile=%s reason=%s",
            profile_id,
            reason,
        )

    async def forward_pending(self) -> int:
        if not self.events_root.is_dir():
            return 0
        forwarded = 0
        changed = False
        present: dict[tuple[str, str], set[str]] = {}
        failed_profiles: set[str] = set()
        for profile_dir in sorted(self.events_root.iterdir()):
            if not profile_dir.is_dir():
                continue
            profile_id = profile_dir.name
            try:
                validate_profile_id(profile_id)
            except PathSecurityError:
                logger.warning(
                    "Skipping invalid download event profile directory: %s",
                    profile_id,
                )
                continue
            events_dir = profile_dir / "events" / "downloads"
            if not events_dir.is_dir():
                continue
            try:
                event_files = sorted(events_dir.glob("*.json"))
            except OSError as exc:
                # A failed scan must not be mistaken for an empty tree:
                # this profile's cursors are exempt from pruning below.
                failed_profiles.add(profile_id)
                logger.warning(
                    "Download event scan failed: profile=%s error_type=%s",
                    profile_id,
                    type(exc).__name__,
                )
                continue
            for event_file in event_files:
                try:
                    event_file.resolve().relative_to(self.events_root.resolve())
                except (OSError, RuntimeError, ValueError):
                    continue
                try:
                    data = json.loads(event_file.read_text(encoding="utf-8"))
                except (OSError, ValueError, UnicodeError) as exc:
                    logger.warning(
                        "Unreadable download event: profile=%s error_type=%s",
                        profile_id,
                        type(exc).__name__,
                    )
                    self._dead_letter(event_file, profile_id, "unreadable")
                    continue
                event, invalid_reason = self._parse_event(data)
                if event is None:
                    logger.warning(
                        "Invalid download event: profile=%s reason=%s",
                        profile_id,
                        invalid_reason,
                    )
                    self._dead_letter(event_file, profile_id, invalid_reason)
                    continue
                if event.profile_id != profile_id:
                    logger.warning(
                        "Download event profile mismatch: directory=%s event=%s",
                        profile_id,
                        event.profile_id,
                    )
                    self._dead_letter(event_file, profile_id, "profile_mismatch")
                    continue
                instance_id = event.runtime_instance_id
                key = event.event_id
                present.setdefault((profile_id, instance_id), set()).add(key)
                if self._is_processed(profile_id, instance_id, key):
                    continue
                if event.state != "completed" or not event.download_path:
                    self._mark_processed(profile_id, instance_id, key)
                    changed = True
                    continue
                try:
                    translated_path = translate_download_path(
                        event.download_path, self.data_root, profile_id
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    logger.warning(
                        "Download path rejected: profile=%s event=%s "
                        "error_type=%s",
                        profile_id,
                        event.event_id,
                        type(exc).__name__,
                    )
                    self._dead_letter(event_file, profile_id, "path_escape")
                    continue
                payload = {
                    "event_id": event.event_id,
                    "profile_id": profile_id,
                    "runtime_instance_id": event.runtime_instance_id,
                    "path": translated_path,
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
        # Only a scan that ran to completion may prune: every early return
        # above (transport error, retryable status) leaves cursors untouched.
        if self._prune(present, failed_profiles) or changed:
            self._save_processed()
        return forwarded

    def _prune(
        self,
        present: dict[tuple[str, str], set[str]],
        failed_profiles: set[str],
    ) -> bool:
        """Drop cursors for instances absent from a complete scan.

        Instances still present keep only the event ids seen this round.
        Profiles whose scan failed keep their cursors verbatim: a read
        failure is not evidence that the instance disappeared.
        """
        changed = False
        for profile_id in list(self._processed):
            if profile_id in failed_profiles:
                continue
            instances = self._processed[profile_id]
            for instance_id in list(instances):
                keys = present.get((profile_id, instance_id))
                if keys is None:
                    del instances[instance_id]
                    changed = True
                    continue
                before = len(instances[instance_id])
                instances[instance_id].intersection_update(keys)
                if len(instances[instance_id]) != before:
                    changed = True
            if not instances:
                del self._processed[profile_id]
                changed = True
        return changed
