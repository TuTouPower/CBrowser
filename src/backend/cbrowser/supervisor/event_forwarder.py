"""Event forwarder and offline disk queue for Supervisor.

AC-004:
- When API is unreachable, events are stored on disk with unique event_id.
- Upon reconnection, events are replayed with deduplication.
- Interacts strictly with /api/v1/internal/supervisor endpoints using Bearer token.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from cbrowser.domain.models import RuntimeEventReportRequest
from cbrowser.supervisor.file_storage import atomic_write_text
from pydantic import ValidationError

logger = logging.getLogger("cbrowser.supervisor.event_forwarder")

DELIVERED = "delivered"
REJECTED = "rejected"
UNAVAILABLE = "unavailable"


class EventForwarder:
    """Queues and forwards runtime events to API via internal RPC."""

    def __init__(
        self,
        api_base_url: str,
        events_spool_dir: Path,
        token_file: Optional[Path | str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_base_url = api_base_url.rstrip("/")
        self.events_spool_dir = Path(events_spool_dir)
        self.events_spool_dir.mkdir(parents=True, exist_ok=True)
        self._token_file = Path(token_file) if token_file else None
        self._external_client = client
        self._client: Optional[httpx.AsyncClient] = None
        self._replay_lock = asyncio.Lock()
        self._spool_lock = asyncio.Lock()
        self._ack_file = self.events_spool_dir / "acknowledged.log"
        self._acknowledged = set(
            self._ack_file.read_text().splitlines() if self._ack_file.exists() else []
        )

    @staticmethod
    def _event_key(event_id: str) -> str:
        return hashlib.sha256(event_id.encode("utf-8")).hexdigest()

    def _sync_directory(self) -> None:
        descriptor = os.open(self.events_spool_dir, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    async def _acknowledge(self, event_data: dict[str, Any], event_file: Path) -> None:
        key = self._event_key(event_data["event_id"])
        async with self._spool_lock:
            if key not in self._acknowledged:
                with self._ack_file.open("a", encoding="utf-8") as output:
                    output.write(key + "\n")
                    output.flush()
                    os.fsync(output.fileno())
                self._sync_directory()
                self._acknowledged.add(key)
            event_file.unlink(missing_ok=True)
            self._sync_directory()

    def _get_bearer_token(self) -> Optional[str]:
        if self._token_file and self._token_file.is_file():
            return self._token_file.read_text(encoding="utf-8").strip()
        return None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._external_client:
            return self._external_client
        if self._client is None or self._client.is_closed:
            headers = {}
            token = self._get_bearer_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            self._client = httpx.AsyncClient(
                base_url=self.api_base_url,
                headers=headers,
                timeout=5.0,
                trust_env=False,
            )
        return self._client

    def _auth_headers(self) -> dict[str, str]:
        token = self._get_bearer_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def emit_event(
        self,
        event_id: str,
        profile_id: str,
        runtime_instance_id: str,
        event_type: str,
        exit_code: int | None = None,
        exit_reason: str | None = None,
        config_version: int = 1,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """Persist the event atomically before attempting API delivery."""
        event_data = {
            "event_id": event_id,
            "profile_id": profile_id,
            "runtime_instance_id": runtime_instance_id,
            "event_type": event_type,
            "exit_code": exit_code,
            "exit_reason": exit_reason,
            "config_version": config_version,
            "payload": payload or {},
        }

        # External event identifiers never become filesystem path components.
        key = self._event_key(event_id)
        event_file = self.events_spool_dir / f"{key}.json"
        async with self._spool_lock:
            if key in self._acknowledged:
                return True
            atomic_write_text(event_file, json.dumps(event_data))

        # 2. Try sending to API
        outcome = await self._send_to_api(event_data)
        if outcome == DELIVERED:
            await self._acknowledge(event_data, event_file)
            return True
        if outcome == REJECTED:
            self._quarantine_event_file(event_file, "rejected")
            return False
        logger.info(f"API unavailable or failed. Event {event_id} queued in spool.")
        return False

    def _quarantine_event_file(self, event_file: Path, reason: str) -> None:
        target_dir = self.events_spool_dir / "quarantine"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            os.replace(event_file, target_dir / event_file.name)
        except OSError as exc:
            logger.warning(
                "Spool quarantine failed: reason=%s error_type=%s",
                reason,
                type(exc).__name__,
            )
            return
        logger.warning("Quarantined spooled runtime event: reason=%s", reason)

    @staticmethod
    def _validate_spooled_event(data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        try:
            record = RuntimeEventReportRequest.model_validate(data)
        except ValidationError:
            return None
        if record.event_type == "exit" and record.exit_code is None:
            return None
        return record.model_dump()

    async def _send_to_api(self, event_data: dict[str, Any]) -> str:
        try:
            client = await self._get_client()
            resp = await client.post(
                "/api/v1/internal/supervisor/runtimes/events",
                headers=self._auth_headers(),
                json=event_data,
            )
            if resp.status_code == 200:
                data = resp.json()
                accepted = data.get("status") == "ok" and data.get("outcome") in {
                    "applied",
                    "duplicate",
                    "stale_instance",
                    "invalid_config_version",
                    "profile_not_found",
                }
                return DELIVERED if accepted else REJECTED
            logger.warning("API rejected runtime event: status=%s", resp.status_code)
            return REJECTED if resp.status_code < 500 else UNAVAILABLE
        except Exception as e:
            logger.debug(f"Network error forwarding event to API: {e}")
            return UNAVAILABLE

    async def replay_spooled_events(self) -> int:
        """Scan spool dir and replay all undelivered events in deterministic order."""
        async with self._replay_lock:
            spooled_files = sorted(self.events_spool_dir.glob("*.json"))
            if not spooled_files:
                return 0

            delivered_count = 0
            for f in spooled_files:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError, UnicodeError) as exc:
                    logger.warning(
                        "Unreadable spooled event quarantined: error_type=%s",
                        type(exc).__name__,
                    )
                    self._quarantine_event_file(f, "unreadable")
                    continue
                validated = self._validate_spooled_event(data)
                if validated is None:
                    self._quarantine_event_file(f, "schema")
                    continue
                if self._event_key(validated["event_id"]) in self._acknowledged:
                    await self._acknowledge(validated, f)
                    delivered_count += 1
                    continue
                outcome = await self._send_to_api(validated)
                if outcome == DELIVERED:
                    await self._acknowledge(validated, f)
                    delivered_count += 1
                elif outcome == REJECTED:
                    self._quarantine_event_file(f, "rejected")
                else:
                    break  # API still down, stop replaying
            return delivered_count

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
