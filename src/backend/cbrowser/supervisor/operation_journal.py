"""Durable results for instance-fenced lifecycle commands; never uses SQLite."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from cbrowser.shared.atomic_write import atomic_write_text

logger = logging.getLogger("cbrowser.supervisor.operation_journal")


class OperationJournal:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def _path(self, operation_id: str) -> Path:
        return self.directory / (
            hashlib.sha256(operation_id.encode()).hexdigest() + ".json"
        )

    def _quarantine(self, path: Path) -> None:
        target = path.with_name(f"{path.name}.corrupt-{uuid.uuid4().hex}")
        try:
            path.replace(target)
        except OSError as exc:
            logger.warning(
                "Operation journal quarantine failed: error_type=%s",
                type(exc).__name__,
            )
            return
        logger.warning("Quarantined corrupt operation journal: %s", target.name)

    def lookup(self, operation_id: str, request: dict) -> dict[str, Any] | None:
        path = self._path(operation_id)
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            record_request = record["request"]
            result = record["result"]
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
            logger.warning(
                "Unreadable operation journal treated as missing: error_type=%s",
                type(exc).__name__,
            )
            self._quarantine(path)
            return None
        if record_request != request:
            raise ValueError("Operation ID was already used for a different request")
        return result

    def complete(self, operation_id: str, request: dict, result: dict) -> None:
        self.lookup(operation_id, request)
        self._write(operation_id, request, result)

    def begin(self, operation_id: str, request: dict) -> dict | None:
        previous = self.lookup(operation_id, request)
        if not self._path(operation_id).exists():
            self._write(operation_id, request, None)
        return previous

    def _write(self, operation_id: str, request: dict, result: dict | None) -> None:
        atomic_write_text(
            self._path(operation_id), json.dumps({"request": request, "result": result})
        )
