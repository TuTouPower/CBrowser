"""t041: fingerprint platform and immutable font set binding.

Adds ``fingerprint_platform`` and ``font_set_id`` to profiles and removes the
retired ``font_bundle`` column. SQLite needs a batch table rebuild for the
column drop, so the whole change runs inside one ``batch_alter_table`` block.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c41f0a2b7d93"
down_revision: str | None = "b7e1c9d4a2f3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "fingerprint_platform",
                sa.String(length=16),
                nullable=False,
                server_default="windows",
            )
        )
        batch_op.add_column(
            sa.Column("font_set_id", sa.String(length=64), nullable=True)
        )
        batch_op.drop_column("font_bundle")


_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: CBrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
