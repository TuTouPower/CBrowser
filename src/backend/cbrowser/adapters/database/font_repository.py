"""t081: persistence for the font set asset catalog.

The API is the only writer of ``font_set_assets``.  Reads return frozen
snapshots so callers never touch detached ORM instances.  Two fences
protect consumers from stale conclusions:

- ``revision`` increments on every applied mutation; consumer-side
  verification results are fenced by (instance, set_id, revision).
- ``state_seq`` increments on every applied mutation as well; an audit
  verdict applies only while the sequence captured when the audit was
  scheduled is still current, so a late verdict can never overwrite a
  newer applied verdict or adoption.  Publishing and repair write font
  files only (never the catalog), so they do not move the fences; a
  repair takes effect through a subsequent audit verdict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from cbrowser.adapters.database.models import FontSetAssetModel
from cbrowser.adapters.database.session import write_transaction
from cbrowser.domain.models import utc_now_iso
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(frozen=True)
class FontAssetRecord:
    platform: str
    set_id: str
    source: str | None
    source_version: str | None
    file_count: int
    total_bytes: int
    integrity: dict
    state: str
    revision: int
    state_seq: int
    verified_at: str | None
    audited_at: str | None
    created_at: str
    updated_at: str

    @property
    def verified(self) -> bool:
        return self.state == "verified"

    @property
    def problems(self) -> list:
        return list(self.integrity.get("problems", []))

    @property
    def detection(self) -> dict:
        return dict(self.integrity.get("detection", {}))


def _snapshot(row: FontSetAssetModel) -> FontAssetRecord:
    return FontAssetRecord(
        platform=row.platform,
        set_id=row.set_id,
        source=row.source,
        source_version=row.source_version,
        file_count=row.file_count,
        total_bytes=row.total_bytes,
        integrity=json.loads(row.integrity or "{}"),
        state=row.state,
        revision=row.revision,
        state_seq=row.state_seq,
        verified_at=row.verified_at,
        audited_at=row.audited_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class FontSetRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self._session_maker = session_maker

    async def get(self, platform: str, set_id: str) -> FontAssetRecord | None:
        async with self._session_maker() as session:
            row = await session.get(FontSetAssetModel, (platform, set_id))
            return _snapshot(row) if row is not None else None

    async def list_all(self) -> list[FontAssetRecord]:
        async with self._session_maker() as session:
            rows = (
                await session.execute(
                    select(FontSetAssetModel).order_by(
                        FontSetAssetModel.platform, FontSetAssetModel.set_id
                    )
                )
            ).scalars().all()
            return [_snapshot(row) for row in rows]

    async def apply_audit_verdict(
        self,
        platform: str,
        set_id: str,
        *,
        expected_seq: int | None,
        ok: bool,
        integrity: dict,
        file_count: int,
        total_bytes: int,
        source: str | None = None,
        source_version: str | None = None,
    ) -> bool:
        """Apply an audit verdict iff its fence is still current.

        ``expected_seq`` is the ``state_seq`` captured when the audit was
        scheduled (``None`` when no catalog row existed: the verdict then
        adopts the set, and applies only if the row is still absent).
        Returns False when the verdict was stale and dropped.
        """
        now = utc_now_iso()
        # t084 (p138): the whole read-then-write runs inside
        # write_transaction so the read snapshot is taken under
        # BEGIN IMMEDIATE; concurrent verdicts serialize instead of
        # colliding with SQLITE_BUSY_SNAPSHOT on commit.
        async with self._session_maker() as session, write_transaction(session):
            row = await session.get(FontSetAssetModel, (platform, set_id))
            if row is None:
                if expected_seq is not None:
                    return False
                row = FontSetAssetModel(
                    platform=platform,
                    set_id=set_id,
                    source=source,
                    source_version=source_version,
                    file_count=file_count,
                    total_bytes=total_bytes,
                    integrity=json.dumps(integrity),
                    state="verified" if ok else "failed",
                    revision=1,
                    state_seq=1,
                    verified_at=now if ok else None,
                    audited_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                try:
                    await session.flush()
                except IntegrityError:
                    await session.rollback()
                    return False
                return True
            if row.state_seq != expected_seq:
                return False
            row.state = "verified" if ok else "failed"
            row.integrity = json.dumps(integrity)
            row.file_count = file_count
            row.total_bytes = total_bytes
            if ok:
                row.verified_at = now
            row.audited_at = now
            row.revision += 1
            row.state_seq += 1
            row.updated_at = now
            return True
