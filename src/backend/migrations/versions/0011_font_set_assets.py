"""0011: font set asset catalog (t081).

Font sets become immutable published resources whose verification
conclusions live in the API-owned catalog instead of being recomputed
by hashing font bytes on every read.  ``font_set_assets`` holds one row
per (platform, set_id): content identity, detection coverage, the
verification state/timestamps and the revision/state-sequence fences
that keep late audit verdicts from overwriting newer state.

Downgrade is unsupported (t056 A60): migrations only move forward; roll
back with a release rollback + data-directory rebuild instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c81f0a11b001"
down_revision: str | None = "8c3f1d0a7b92"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    op.create_table(
        "font_set_assets",
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("set_id", sa.String(64), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("source_version", sa.String(255), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("integrity", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state_seq", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.String(64), nullable=True),
        sa.Column("audited_at", sa.String(64), nullable=True),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("platform", "set_id"),
    )


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
