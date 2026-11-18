"""0011: durable profile deletion intents (t078).

Adds ``profile_deletions``: one row per deletion target with its
lifecycle stage, so a stop-then-delete operation survives client
disconnects and service restarts and can be queried, resumed and
retried per target.

Downgrade is unsupported (t056 A60): migrations only move forward; roll
back with a release rollback + data-directory rebuild instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c41d9a02e6b7"
down_revision: str | None = "8c3f1d0a7b92"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    op.create_table(
        "profile_deletions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_name", sa.String(255), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("failed_stage", sa.String(32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(64), nullable=False),
    )
    op.create_index(
        "idx_profile_deletions_batch", "profile_deletions", ["batch_id"]
    )
    op.create_index(
        "idx_profile_deletions_profile", "profile_deletions", ["profile_id"]
    )
    # At most one open (non-done) intent per profile, enforced by the
    # database: concurrent duplicate submissions cannot create two
    # intents for the same target (t078 AC-004).
    op.create_index(
        "uq_profile_deletions_open_profile",
        "profile_deletions",
        ["profile_id"],
        unique=True,
        sqlite_where=sa.text("stage != 'done'"),
    )


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
