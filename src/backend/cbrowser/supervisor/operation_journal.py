"""Durable results for instance-fenced lifecycle commands; never uses SQLite."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cbrowser.supervisor.file_storage import atomic_write_text


class OperationJournal:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def _path(self, operation_id: str) -> Path:
        return self.directory / (
            hashlib.sha256(operation_id.encode()).hexdigest() + ".json"
        )

    def lookup(self, operation_id: str, request: dict) -> dict[str, Any] | None:
        path = self._path(operation_id)
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["request"] != request:
            raise ValueError("Operation ID was already used for a different request")
        return record["result"]

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
