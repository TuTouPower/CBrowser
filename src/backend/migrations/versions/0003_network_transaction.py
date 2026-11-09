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
ACTIVE_KEY = "network.active_operation"
CURRENT_KEY = "network.transaction.current"

_TERMINAL_PHASES = frozenset({"completed", "failed"})


def _backfill_record(record: dict) -> None:
    record.setdefault("decision", "pending")
    record.setdefault("transaction_phase", "pending")
    record.setdefault("execution_generation", 0)
    record.setdefault("recovery_complete", True)


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
        _backfill_record(record)
        bind.execute(
            sa.text("UPDATE settings SET value = :value WHERE key = :key"),
            {"value": json.dumps(record), "key": key},
        )
    # A pre-A35 crash leaves network.active_operation as a plain operation
    # snapshot (no recovery fields) with no transaction.current pointer, so
    # boot recovery (which arbitrates via the current pointer) reports "none"
    # while begin_network_transaction still sees a pending active row: every
    # later apply is rejected as "already in progress" forever. Backfill the
    # active row with the same recovery defaults, then either link it from
    # the current pointer so recovery can arbitrate it, or drop it when it
    # is a terminal/orphan leftover that no recovery path could consume.
    active_row = bind.execute(
        sa.text("SELECT value FROM settings WHERE key = :key"),
        {"key": ACTIVE_KEY},
    ).fetchone()
    if active_row is not None:
        try:
            active_record = json.loads(active_row[0])
        except (TypeError, ValueError):
            active_record = None
        if not isinstance(active_record, dict) or "decision" in active_record:
            pass
        elif active_record.get("phase") in _TERMINAL_PHASES:
            bind.execute(
                sa.text("DELETE FROM settings WHERE key = :key"),
                {"key": ACTIVE_KEY},
            )
        else:
            _backfill_record(active_record)
            operation_id = active_record.get("operation_id")
            op_row = (
                bind.execute(
                    sa.text("SELECT value FROM settings WHERE key = :key"),
                    {"key": f"{OP_PREFIX}{operation_id}"},
                ).fetchone()
                if operation_id
                else None
            )
            if not isinstance(operation_id, str) or not operation_id or op_row is None:
                bind.execute(
                    sa.text("DELETE FROM settings WHERE key = :key"),
                    {"key": ACTIVE_KEY},
                )
            else:
                bind.execute(
                    sa.text("UPDATE settings SET value = :value WHERE key = :key"),
                    {"value": json.dumps(active_record), "key": ACTIVE_KEY},
                )
                current_row = bind.execute(
                    sa.text("SELECT value FROM settings WHERE key = :key"),
                    {"key": CURRENT_KEY},
                ).fetchone()
                if current_row is None:
                    bind.execute(
                        sa.text(
                            "INSERT INTO settings (key, value, updated_at) "
                            "VALUES (:key, :value, :updated_at)"
                        ),
                        {
                            "key": CURRENT_KEY,
                            "value": operation_id,
                            "updated_at": "1970-01-01T00:00:00+00:00",
                        },
                    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM settings WHERE key = :key"),
        {"key": GENERATION_KEY},
    )
