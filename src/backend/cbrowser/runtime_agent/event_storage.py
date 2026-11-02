"""Atomic, concurrent-safe persistent event and state storage."""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from .protocol import DownloadEventRecord, RuntimeEventRecord, RuntimeStateRecord
from .security import validate_runtime_id

logger = logging.getLogger("cbrowser.runtime_agent.event_storage")

MAX_RUNTIME_EVENTS_PER_INSTANCE = 100
MAX_DOWNLOAD_EVENTS_PER_INSTANCE = 100
_DOWNLOAD_INDEX_VERSION = 1


class StorageError(RuntimeError):
    """Base exception for runtime storage failures."""


class CorruptStateError(StorageError):
    """Raised when the persistent state file is corrupted or unparseable."""


def _sync_directory(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_directory(path: Path) -> None:
    """Persist newly created directory links as well as their future files."""
    missing = []
    parent = path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    if not parent.is_dir():
        raise NotADirectoryError("Runtime storage parent is not a directory")
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            if not directory.is_dir():
                raise
        _sync_directory(directory.parent)


def atomic_write_json(file_path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON data to file with fsync and directory sync."""
    tmp_path = file_path.with_name(f"{file_path.name}.tmp.{uuid.uuid4().hex}")
    try:
        _ensure_directory(file_path.parent)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)

        # A successful replace alone does not acknowledge durable directory
        # metadata. Unsupported synchronization is a failure too.
        _sync_directory(file_path.parent)
    except StorageError:
        raise
    except Exception as exc:
        logger.error(
            "Failed to atomic_write_json to %s: %s", file_path.name, type(exc).__name__
        )
        raise StorageError(f"Atomic write failed for {file_path.name}") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


class EventStorage:
    """Manages persistent events and runtime state on the filesystem."""

    def __init__(self, run_dir: Path | str) -> None:
        self.run_dir = Path(run_dir)
        self.runtime_events_dir = self.run_dir / "events" / "runtime"
        self.download_events_dir = self.run_dir / "events" / "downloads"
        self.download_index_file = self.run_dir / "events" / "download-index.json"
        self._download_index: dict[str, dict[str, Any]] | None = None
        self._download_index_lock = threading.RLock()
        self.state_file = self.run_dir / "state.json"
        try:
            _ensure_directory(self.runtime_events_dir)
            _ensure_directory(self.download_events_dir)
        except OSError:
            raise StorageError("Runtime storage directory unavailable") from None

    def save_runtime_event(self, event: RuntimeEventRecord) -> None:
        """Atomically persist a runtime event record with unique event ID filename."""
        instance = validate_runtime_id(event.runtime_instance_id)
        target = self.runtime_events_dir / instance / f"{event.event_id}.json"
        atomic_write_json(target, event.model_dump())
        self._prune_runtime_events(target.parent)
        logger.info(
            "Persisted runtime event: %s (type=%s)", event.event_id, event.event_type
        )

    @staticmethod
    def _prune_runtime_events(directory: Path) -> None:
        """Keep only the newest events; status queries never need full history."""
        try:
            files = sorted(
                directory.glob("*.json"), key=lambda p: p.stat().st_mtime_ns
            )
        except OSError:
            return
        for stale in files[:-MAX_RUNTIME_EVENTS_PER_INSTANCE]:
            stale.unlink(missing_ok=True)

    def get_runtime_events(self) -> list[RuntimeEventRecord]:
        """Read and return all persisted runtime event records."""
        return self._read_runtime_events(self.runtime_events_dir, recursive=True)

    def _read_runtime_events(
        self, directory: Path, *, recursive: bool = False
    ) -> list[RuntimeEventRecord]:
        events: list[RuntimeEventRecord] = []
        files = directory.rglob("*.json") if recursive else directory.glob("*.json")
        for item in sorted(files):
            try:
                with open(item, "r", encoding="utf-8") as f:
                    data = json.load(f)
                events.append(RuntimeEventRecord.model_validate(data))
            except Exception as e:
                logger.error(
                    "Corrupt runtime event file %s: %s", item.name, type(e).__name__
                )
                raise StorageError(f"Corrupt runtime event file: {item.name}") from e
        return events

    def _download_files(self) -> set[str]:
        try:
            return {item.name for item in self.download_events_dir.glob("*.json")}
        except OSError:
            return set()

    def _read_download_index(self) -> dict[str, dict[str, Any]] | None:
        try:
            raw = json.loads(self.download_index_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return None
        if not isinstance(raw, dict) or raw.get("version") != _DOWNLOAD_INDEX_VERSION:
            return None
        events = raw.get("events")
        if not isinstance(events, dict):
            return None
        index: dict[str, dict[str, Any]] = {}
        for event_id, entry in events.items():
            if (
                isinstance(event_id, str)
                and isinstance(entry, dict)
                and isinstance(entry.get("file"), str)
                and isinstance(entry.get("instance"), str)
                and isinstance(entry.get("created_at"), str)
            ):
                index[event_id] = {
                    "file": entry["file"],
                    "instance": entry["instance"],
                    "created_at": entry["created_at"],
                }
        return index

    def _write_download_index(self, index: dict[str, dict[str, Any]]) -> None:
        atomic_write_json(
            self.download_index_file,
            {"version": _DOWNLOAD_INDEX_VERSION, "events": index},
        )

    def _prune_download_index(self, index: dict[str, dict[str, Any]]) -> None:
        by_instance: dict[str, list[str]] = defaultdict(list)
        for event_id, entry in index.items():
            by_instance[entry["instance"]].append(event_id)
        for event_ids in by_instance.values():
            if len(event_ids) <= MAX_DOWNLOAD_EVENTS_PER_INSTANCE:
                continue
            event_ids.sort(
                key=lambda event_id: (index[event_id]["created_at"], event_id)
            )
            for event_id in event_ids[:-MAX_DOWNLOAD_EVENTS_PER_INSTANCE]:
                entry = index.pop(event_id)
                try:
                    (self.download_events_dir / entry["file"]).unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning(
                        "Failed to prune download event %s: %s",
                        entry["file"],
                        type(exc).__name__,
                    )

    def _quarantine_download_event(self, item: Path) -> None:
        quarantine = self.download_events_dir / "quarantine"
        try:
            quarantine.mkdir(parents=True, exist_ok=True)
            os.replace(item, quarantine / item.name)
        except OSError as exc:
            logger.warning(
                "Download event quarantine failed: %s", type(exc).__name__
            )

    def _rebuild_download_index(self) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        try:
            files = sorted(self.download_events_dir.glob("*.json"))
        except OSError:
            files = []
        for item in files:
            try:
                data = json.loads(item.read_text(encoding="utf-8"))
                event = DownloadEventRecord.model_validate(data)
            except Exception as exc:
                logger.error(
                    "Corrupt download event file %s: %s",
                    item.name,
                    type(exc).__name__,
                )
                self._quarantine_download_event(item)
                continue
            index[event.event_id] = {
                "file": item.name,
                "instance": event.runtime_instance_id,
                "created_at": event.created_at,
            }
        self._prune_download_index(index)
        self._write_download_index(index)
        return index

    def _get_download_index(self, *, reconcile: bool) -> dict[str, dict[str, Any]]:
        if self._download_index is None:
            index = self._read_download_index()
            if index is None or {
                entry["file"] for entry in index.values()
            } != self._download_files():
                index = self._rebuild_download_index()
            self._download_index = index
        elif reconcile and {
            entry["file"] for entry in self._download_index.values()
        } != self._download_files():
            self._download_index = self._rebuild_download_index()
        return self._download_index

    def save_download_event(self, event: DownloadEventRecord) -> None:
        """Atomically persist a download event and incrementally update its index."""
        target = self.download_events_dir / f"{event.event_id}.json"
        atomic_write_json(target, event.model_dump())
        with self._download_index_lock:
            index = self._get_download_index(reconcile=False)
            index[event.event_id] = {
                "file": target.name,
                "instance": event.runtime_instance_id,
                "created_at": event.created_at,
            }
            self._prune_download_index(index)
            self._write_download_index(index)
            self._download_index = index
        logger.info(
            "Persisted download event: %s (state=%s)", event.event_id, event.state
        )

    def get_download_events(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[DownloadEventRecord]:
        """Return indexed download events, oldest first, with bounded pagination."""
        if offset < 0 or (limit is not None and limit < 0):
            raise ValueError("Invalid download event pagination")
        with self._download_index_lock:
            index = self._get_download_index(reconcile=True)
            ordered = sorted(
                index.items(), key=lambda item: (item[1]["created_at"], item[0])
            )
            upper = None if limit is None else offset + limit
            selected = ordered[offset:upper]
            events: list[DownloadEventRecord] = []
            missing: list[str] = []
            for event_id, entry in selected:
                item = self.download_events_dir / entry["file"]
                try:
                    with open(item, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    events.append(DownloadEventRecord.model_validate(data))
                except FileNotFoundError:
                    missing.append(event_id)
                except Exception as e:
                    logger.error(
                        "Corrupt download event file %s: %s",
                        item.name,
                        type(e).__name__,
                    )
                    self._quarantine_download_event(item)
                    missing.append(event_id)
                    continue
            if missing:
                for event_id in missing:
                    index.pop(event_id, None)
                self._write_download_index(index)
                self._download_index = index
        return events

    def save_state(self, state: RuntimeStateRecord) -> None:
        """Atomically persist current runtime state."""
        instance = validate_runtime_id(state.runtime_instance_id)
        atomic_write_json(
            self.run_dir / "instances" / instance / "state.json", state.model_dump()
        )
        # Discovery cache for an offline Agent without transient runner_info.
        # Live decisions always select the explicit instance journal below.
        atomic_write_json(self.state_file, state.model_dump())
        logger.info(
            "Persisted runtime state: %s (code=%s, reason=%s)",
            state.state,
            state.exit_code,
            state.exit_reason,
        )

    def get_state(self) -> RuntimeStateRecord | None:
        """Read the last-written discovery cache, never infer a current generation."""
        return self._read_state(self.state_file)

    def _read_state(self, path: Path) -> RuntimeStateRecord | None:
        if not path.exists():
            return None
        try:
            return RuntimeStateRecord.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except Exception as exc:  # noqa: BLE001 - any state deserialization failure raises CorruptStateError
            logger.error("Corrupt runtime state (%s)", type(exc).__name__)
            raise CorruptStateError("Corrupt runtime state") from None

    def get_instance_state(
        self,
        profile_id: str,
        runtime_instance_id: str,
        *,
        recover_terminal: bool = False,
    ) -> RuntimeStateRecord | None:
        """Select a generation without accepting another instance's late cache write."""
        validate_runtime_id(profile_id)
        instance = validate_runtime_id(runtime_instance_id)
        cached = self.get_state()
        if cached and cached.profile_id != profile_id:
            raise StorageError("Runtime storage profile mismatch")
        state = self._read_state(self.run_dir / "instances" / instance / "state.json")
        if state and (
            state.profile_id != profile_id or state.runtime_instance_id != instance
        ):
            raise StorageError("Runtime state identity mismatch")
        if recover_terminal:
            events = self._read_runtime_events(self.runtime_events_dir / instance)
            terminal = []
            for event in events:
                if (
                    event.profile_id != profile_id
                    or event.runtime_instance_id != instance
                ):
                    raise StorageError("Runtime event identity mismatch")
                if (
                    event.event_type == "exit"
                    or event.exit_reason == "process_observation_lost"
                ):
                    terminal.append(event)
            if len(terminal) > 1:
                raise StorageError("Conflicting runtime terminal facts")
            if terminal:
                event = terminal[0]
                if state and state.config_version != event.config_version:
                    raise StorageError("Runtime terminal version mismatch")
                if event.event_type == "exit" and event.exit_code is None:
                    raise StorageError("Runtime exit status is missing")
                payload_code = event.payload.get("exit_code")
                return RuntimeStateRecord(
                    profile_id=profile_id,
                    runtime_instance_id=instance,
                    config_version=event.config_version,
                    state="stopped" if event.event_type == "exit" else "error",
                    exit_code=event.exit_code
                    if event.event_type == "exit"
                    else (payload_code if type(payload_code) is int else None),
                    exit_reason=event.exit_reason,
                    browser_pid=state.browser_pid if state else None,
                    updated_at=event.created_at,
                )
        if state is None and cached and cached.runtime_instance_id == instance:
            raise CorruptStateError("Runtime instance state is missing")
        return state
