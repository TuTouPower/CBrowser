"""A35: seed the exclusive network execution generation counter.

Recovery fields live inside the existing network.operation.* records; no
parallel ledger table is introduced. This revision seeds the generation
counter and backfills default recovery fields for pre-existing operation
records so a restart can arbitrate them via the single DB authority.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a35c0f1e7b42"
down_revision: str | None = "c41f0a2b7d93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GENERATION_KEY = "network.execution_generation"
OP_PREFIX = "network.operation."


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT value FROM settings WHERE key = :key"),
        {"key": GENERATION_KEY},
    ).fetchone()
    if existing is None:
        bind.execute(
            sa.text(
                "INSERT INTO settings (key, value, updated_at) "
                "VALUES (:key, :value, :updated_at)"
            ),
            {
                "key": GENERATION_KEY,
                "value": "0",
                "updated_at": "1970-01-01T00:00:00+00:00",
            },
        )
    rows = bind.execute(
        sa.text("SELECT key, value FROM settings WHERE key LIKE :prefix"),
        {"prefix": OP_PREFIX + "%"},
    ).fetchall()
    for key, value in rows:
        try:
            record = json.loads(value)
        except (TypeError, ValueError):
            continue
        if not isinstance(record, dict) or "decision" in record:
            continue
        record.setdefault("decision", "pending")
        record.setdefault("transaction_phase", "pending")
        record.setdefault("execution_generation", 0)
        record.setdefault("recovery_complete", True)
        bind.execute(
            sa.text("UPDATE settings SET value = :value WHERE key = :key"),
            {"value": json.dumps(record), "key": key},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM settings WHERE key = :key"),
        {"key": GENERATION_KEY},
    )
