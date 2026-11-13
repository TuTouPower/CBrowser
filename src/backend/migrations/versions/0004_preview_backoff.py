"""0004: restore preview epoch and supervisor backoff columns (t040/t039).

0001_baseline.py is immutable (t035): the t039 backoff deadline facts
(backoff_started_at/next_retry_at) and the t040 preview policy epoch plus
preview capture timestamp (capture_preview_epoch/preview_captured_at) were
added to 0001 in place and are moved here as an incremental migration.
Definitions match 0001's (mutated) server_defaults: the single NOT NULL
column carries server_default="0" so existing rows are backfilled, the
three runtime columns are nullable with no default.

The columns are added unconditionally (t056 A60): a database whose tables
already carry one of these columns in a different shape is a historical
mixed shape and must fail loudly instead of being silently stamped to
head. Downgrade is unsupported: migrations only move forward.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0e2ab6553470"
down_revision: str | None = "a35c0f1e7b42"
branch_labels: str | None = None
depends_on: str | None = None

_RUNTIME_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "backoff_started_at",
        sa.Column("backoff_started_at", sa.String(length=64), nullable=True),
    ),
    (
        "next_retry_at",
        sa.Column("next_retry_at", sa.String(length=64), nullable=True),
    ),
    (
        "preview_captured_at",
        sa.Column("preview_captured_at", sa.String(length=64), nullable=True),
    ),
)

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: CBrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "capture_preview_epoch",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
    with op.batch_alter_table("profile_runtimes") as batch_op:
        for _, column in _RUNTIME_COLUMNS:
            batch_op.add_column(column)


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
