"""Durable results for instance-fenced lifecycle commands; never uses SQLite."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from cbrowser.supervisor.file_storage import atomic_write_text

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

    def network_command_id(
        self,
        operation_id: str,
        phase: str,
        resource: str,
        request: dict | None = None,
    ) -> str:
        # P1-A generation fencing: the same operation/resource at different
        # execution generations are different commands. The generation is
        # derived from the request so callers cannot forget it; a request
        # without any generation falls back to the legacy key (no fencing).
        generation: object = None
        if isinstance(request, dict):
            generation = request.get("execution_generation")
            if generation is None:
                generation = request.get("generation")
        if generation is None:
            return f"network:{operation_id}:{phase}:{resource}"
        return f"network:{operation_id}:{generation}:{phase}:{resource}"

    def begin_network_receipt(
        self, operation_id: str, phase: str, resource: str, request: dict
    ) -> dict | None:
        return self.begin(
            self.network_command_id(operation_id, phase, resource, request),
            request,
        )

    def complete_network_receipt(
        self,
        operation_id: str,
        phase: str,
        resource: str,
        request: dict,
        result: dict,
    ) -> None:
        self.complete(
            self.network_command_id(operation_id, phase, resource, request),
            request,
            result,
        )

    def network_receipt(
        self, operation_id: str, phase: str, resource: str, request: dict
    ) -> dict[str, Any] | None:
        return self.lookup(
            self.network_command_id(operation_id, phase, resource, request),
            request,
        )

    def network_receipt_verified(
        self, operation_id: str, phase: str, resource: str, request: dict
    ) -> bool:
        receipt = self.network_receipt(operation_id, phase, resource, request)
        return bool(
            receipt
            and receipt.get("status") == "ok"
            and receipt.get("docker_verified") is True
        )

    def _network_execution_request(
        self,
        operation_id: str,
        generation: int,
        candidate_hash: str,
        restoring: bool,
    ) -> dict[str, Any]:
        return {
            "operation_id": operation_id,
            "execution_generation": generation,
            "candidate_hash": candidate_hash,
            "restoring": restoring,
        }

    def record_network_execution(
        self,
        operation_id: str,
        generation: int,
        candidate_hash: str,
        result: dict,
        *,
        restoring: bool = False,
    ) -> None:
        request = self._network_execution_request(
            operation_id, generation, candidate_hash, restoring
        )
        phase = "compensating" if restoring else "installing"
        self.complete_network_receipt(
            operation_id, phase, "caddy-execution", request, result
        )

    def network_execution_receipt(
        self,
        operation_id: str,
        generation: int,
        candidate_hash: str,
        *,
        restoring: bool = False,
    ) -> dict[str, Any] | None:
        request = self._network_execution_request(
            operation_id, generation, candidate_hash, restoring
        )
        phase = "compensating" if restoring else "installing"
        return self.network_receipt(
            operation_id, phase, "caddy-execution", request
        )

    def _write(self, operation_id: str, request: dict, result: dict | None) -> None:
        atomic_write_text(
            self._path(operation_id), json.dumps({"request": request, "result": result})
        )
