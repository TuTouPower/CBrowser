"""0004: restore preview epoch and supervisor backoff columns (t040/t039).

0001_baseline_v2.py is immutable (t035): the t039 backoff deadline facts
(backoff_started_at/next_retry_at) and the t040 preview policy epoch plus
preview capture timestamp (capture_preview_epoch/preview_captured_at) were
added to 0001 in place and are moved here as an incremental migration.
Definitions match 0001's (mutated) server_defaults: the single NOT NULL
column carries server_default="0" so existing rows are backfilled, the
three runtime columns are nullable with no default.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0e2ab6553470"
down_revision: str | None = "a35c0f1e7b42"
branch_labels: str | None = None
depends_on: str | None = None


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
        batch_op.add_column(
            sa.Column("backoff_started_at", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("next_retry_at", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("preview_captured_at", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("profile_runtimes") as batch_op:
        batch_op.drop_column("preview_captured_at")
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("backoff_started_at")
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.drop_column("capture_preview_epoch")
