"""Add per-profile CJK font bundle column with a no-CJK default.

Revision ID: 0007_font_bundle
Revises: 0006_snapshot_modes
Create Date: 2026-11-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_font_bundle"
down_revision = "0006_snapshot_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        batch.add_column(
            sa.Column(
                "font_bundle",
                sa.String(32),
                nullable=False,
                server_default="none",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        batch.drop_column("font_bundle")
