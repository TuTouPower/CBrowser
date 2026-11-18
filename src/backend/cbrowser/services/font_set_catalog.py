"""t081: font set asset catalog — the single verification authority.

Published font sets are immutable resources.  This service owns every
full-content verification of them:

- **Adoption** (startup / first takeover / recovery): sets found on the
  fonts volume without a verified catalog record are fully verified
  once and recorded; a set becomes selectable/startable only through
  this path or an explicit audit.
- **Explicit audit**: re-verifies one set off the event loop, bounded
  by ``AUDIT_CONCURRENCY``, deduplicated per set while in flight.  The
  verdict is fenced by the catalog ``state_seq`` captured at scheduling
  time; a verdict that arrives after a newer applied verdict or
  adoption is dropped, never applied.  Publishing/repair writes files
  only and takes effect through a subsequent audit; the failure
  direction is closed (a stale verdict can at worst mark a set
  unavailable until the next audit, never verify damaged content).
- **Reads never verify**: list / runtime / binding consumers read the
  catalog records only — zero font-body opens, zero integrity hashes,
  independent of font byte size.

A failed audit marks the asset unavailable (new starts are rejected by
the binding validation and by the Supervisor's own mounted-set check);
a later successful audit or a controlled re-import + audit restores it
under a new revision.  Nothing here deletes or rebuilds browser user
data.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from cbrowser import font_sets
from cbrowser.adapters.database.font_repository import (
    FontAssetRecord,
    FontSetRepository,
)

LOGGER = logging.getLogger(__name__)

# Production-declared bound for concurrent full-content verifications
# (audits + adoptions).  Reads never consume a slot.
AUDIT_CONCURRENCY = 2


def _verify_directory(root: Path | None, platform: str, set_id: str) -> dict:
    """Full verification of one published set (runs on a worker thread)."""
    if root is None:
        return {
            "ok": False,
            "integrity": {
                "ok": False,
                "problems": ["font root is not configured"],
                "file_count": 0,
                "detection": {},
            },
            "file_count": 0,
            "total_bytes": 0,
            "source": None,
            "source_version": None,
        }
    directory = root / platform / set_id
    if not directory.is_dir():
        return {
            "ok": False,
            "integrity": {
                "ok": False,
                "problems": ["font set directory is missing"],
                "file_count": 0,
                "detection": {},
            },
            "file_count": 0,
            "total_bytes": 0,
            "source": None,
            "source_version": None,
        }
    integrity = font_sets.check_font_set(directory)
    found = font_sets.get_font_set(platform, set_id, root=root)
    if found is None:
        # get_font_set rejects a set whose manifest is missing or whose
        # declared platform differs from the directory platform (t053
        # A20).  check_font_set alone has no platform comparison, so
        # without this gate a foreign-platform set would be recorded
        # verified and become bindable while the Supervisor rejects it.
        integrity = dict(integrity)
        integrity["ok"] = False
        integrity["problems"] = list(integrity.get("problems", [])) + [
            "manifest is missing or its platform does not match "
            "the directory platform"
        ]
    manifest = found[1] if found is not None else {}
    total_bytes = 0
    for path in directory.iterdir():
        if path.is_file():
            try:
                total_bytes += path.stat().st_size
            except OSError:
                continue
    return {
        "ok": bool(integrity.get("ok")),
        "integrity": integrity,
        "file_count": int(integrity.get("file_count", 0)),
        "total_bytes": total_bytes,
        "source": manifest.get("source"),
        "source_version": manifest.get("source_version"),
    }


class FontSetCatalogService:
    def __init__(
        self,
        repository: FontSetRepository,
        fonts_root: Path | str | None = None,
    ):
        self._repo = repository
        self._fonts_root = Path(fonts_root) if fonts_root is not None else None
        self._semaphore = asyncio.Semaphore(AUDIT_CONCURRENCY)
        self._inflight: dict[tuple[str, str], asyncio.Task] = {}
        # Catalog writes are tiny but SQLite admits one writer; the
        # expensive verification stays parallel while verdict
        # application is serialized, so concurrent audits can never
        # lose a record to a database-lock error.
        self._write_lock = asyncio.Lock()

    def _root(self) -> Path | None:
        if self._fonts_root is not None:
            return self._fonts_root
        return font_sets.manifest._resolve_root(None)

    def root_configured(self) -> bool:
        """Whether a font root is configured for this process at all.

        Deployments always configure one (deploy.sh exports
        CBROWSER_FONTS_DIR into the release env); a process without one
        has the font subsystem out of scope, which Profile creation
        treats differently from "configured but the platform has no
        verified set" (t075, AC-005)."""
        return self._root() is not None

    # -- reads (never verify) -------------------------------------------------

    async def list_assets(self) -> list[FontAssetRecord]:
        return await self._repo.list_all()

    async def get_asset(
        self, platform: str, set_id: str
    ) -> FontAssetRecord | None:
        return await self._repo.get(platform, set_id)

    async def is_bindable(self, platform: str, set_id: str) -> bool:
        record = await self._repo.get(platform, set_id)
        return record is not None and record.verified

    async def default_set_id(self, platform: str) -> str | None:
        """Backend-chosen default: the most recently *verified* set for
        the platform (ties broken by set_id) — a set that was just
        adopted, audited or repaired-and-reverified wins over an older
        untouched one.  Computed from catalog metadata only, never by
        scanning font bytes."""
        records = [
            record
            for record in await self._repo.list_all()
            if record.platform == platform and record.verified
        ]
        if not records:
            return None
        records.sort(
            key=lambda record: (
                record.verified_at or record.created_at,
                record.set_id,
            )
        )
        return records[-1].set_id

    # -- verification engine --------------------------------------------------

    def audit_in_flight(self, platform: str, set_id: str) -> bool:
        task = self._inflight.get((platform, set_id))
        return task is not None and not task.done()

    async def request_audit(self, platform: str, set_id: str) -> str:
        """Schedule an audit, or report the one already in flight."""
        key = (platform, set_id)
        existing = self._inflight.get(key)
        if existing is not None and not existing.done():
            return "in_flight"
        task = asyncio.create_task(self._run_audit(platform, set_id))
        self._inflight[key] = task

        def _clear(done: asyncio.Task, key=key, task=task) -> None:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)

        task.add_done_callback(_clear)
        return "scheduled"

    async def wait_idle(self) -> None:
        while True:
            tasks = [t for t in self._inflight.values() if not t.done()]
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=True)

    async def audit_and_wait(self, platform: str, set_id: str) -> FontAssetRecord | None:
        await self.request_audit(platform, set_id)
        await self.wait_idle()
        return await self._repo.get(platform, set_id)

    async def _run_audit(self, platform: str, set_id: str) -> None:
        try:
            await self._run_audit_inner(platform, set_id)
        except Exception:  # noqa: BLE001 - audits must never crash the API
            LOGGER.exception(
                "Font audit failed for %s/%s; catalog state unchanged",
                platform,
                set_id,
            )

    async def _run_audit_inner(self, platform: str, set_id: str) -> None:
        record = await self._repo.get(platform, set_id)
        expected_seq = record.state_seq if record is not None else None
        root = self._root()
        async with self._semaphore:
            result = await asyncio.to_thread(
                _verify_directory, root, platform, set_id
            )
        async with self._write_lock:
            applied = await self._repo.apply_audit_verdict(
                platform,
                set_id,
                expected_seq=expected_seq,
                ok=result["ok"],
                integrity=result["integrity"],
                file_count=result["file_count"],
                total_bytes=result["total_bytes"],
                source=result["source"],
                source_version=result["source_version"],
            )
        if not applied:
            LOGGER.info(
                "Dropped stale font audit verdict for %s/%s (superseded)",
                platform,
                set_id,
            )

    async def adopt_all(self) -> None:
        """Verify and record every published set lacking a verified row.

        Directory enumeration reads names only — no font bytes.  Sets
        already verified are skipped, so recovery and repeat adoption
        are idempotent; staging leftovers from an interrupted publish
        never match the set-id pattern and are never adopted.
        """
        root = self._root()
        if root is None or not root.is_dir():
            return
        for platform in font_sets.PLATFORMS:
            platform_dir = root / platform
            if not platform_dir.is_dir():
                continue
            for set_dir in sorted(platform_dir.iterdir()):
                if not set_dir.is_dir():
                    continue
                if not font_sets.manifest.SET_ID_PATTERN.fullmatch(set_dir.name):
                    continue
                record = await self._repo.get(platform, set_dir.name)
                if record is not None and record.verified:
                    continue
                await self.request_audit(platform, set_dir.name)
        await self.wait_idle()
