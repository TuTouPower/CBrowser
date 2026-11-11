"""0004: restore preview epoch and supervisor backoff columns (t040/t039).

0001_baseline.py is immutable (t035): the t039 backoff deadline facts
(backoff_started_at/next_retry_at) and the t040 preview policy epoch plus
preview capture timestamp (capture_preview_epoch/preview_captured_at) were
added to 0001 in place and are moved here as an incremental migration.
Definitions match 0001's (mutated) server_defaults: the single NOT NULL
column carries server_default="0" so existing rows are backfilled, the
three runtime columns are nullable with no default.

Idempotency: databases created from the 1a6ec51-era 0001 already contain
all four columns while stamped at 0002/0003 (e.g. live databases
from the 1a6ec51 era). The
upgrade only adds columns reported missing by the inspector, and the
downgrade only drops columns still present, so re-running this revision
against either shape is a no-op instead of a duplicate-column failure.
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


def _existing_columns(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    try:
        return {col["name"] for col in insp.get_columns(table_name)}
    except sa.exc.NoSuchTableError:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    if "capture_preview_epoch" not in _existing_columns(bind, "profiles"):
        with op.batch_alter_table("profiles") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "capture_preview_epoch",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
    missing = [
        (name, column)
        for name, column in _RUNTIME_COLUMNS
        if name not in _existing_columns(bind, "profile_runtimes")
    ]
    if missing:
        with op.batch_alter_table("profile_runtimes") as batch_op:
            for _, column in missing:
                batch_op.add_column(column)


def downgrade() -> None:
    bind = op.get_bind()
    present = _existing_columns(bind, "profile_runtimes")
    drop_runtimes = [name for name, _ in reversed(_RUNTIME_COLUMNS) if name in present]
    if drop_runtimes:
        with op.batch_alter_table("profile_runtimes") as batch_op:
            for name in drop_runtimes:
                batch_op.drop_column(name)
    if "capture_preview_epoch" in _existing_columns(bind, "profiles"):
        with op.batch_alter_table("profiles") as batch_op:
            batch_op.drop_column("capture_preview_epoch")
