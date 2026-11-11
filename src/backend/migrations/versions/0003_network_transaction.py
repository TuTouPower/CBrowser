"""A35: seed the exclusive network execution generation counter.

Recovery fields live inside the existing network.operation.* records; no
parallel ledger table is introduced. This revision seeds the generation
counter.

The historical mixed-shape patch branches that backfilled recovery
fields into pre-existing operation records and repaired the
network.active_operation pointer were deleted in t056 (A60): under the
zero-compatibility rule a migration must not silently repair unknown
legacy shapes — a database in such a shape is refused by the migration
guard (LegacySchemaError) instead. The network transaction state itself
was deleted by t054 (migration 0008 drops every network.* row).

Downgrade is unsupported (t056 A60): migrations only move forward.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a35c0f1e7b42"
down_revision: str | None = "c41f0a2b7d93"
branch_labels: str | None = None
depends_on: str | None = None

GENERATION_KEY = "network.execution_generation"

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: CBrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


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


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
