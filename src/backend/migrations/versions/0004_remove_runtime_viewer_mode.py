"""Remove single-value runtime_mode and viewer_mode columns.

Revision ID: 0004_remove_modes
Revises: 0003_artifact_storage
Create Date: 2026-11-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_remove_modes"
down_revision = "0003_artifact_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        batch.drop_column("runtime_mode")
        batch.drop_column("viewer_mode")


def downgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        batch.add_column(
            sa.Column("runtime_mode", sa.String(32), nullable=False, server_default="docker")
        )
        batch.add_column(
            sa.Column("viewer_mode", sa.String(32), nullable=False, server_default="webrtc")
        )
