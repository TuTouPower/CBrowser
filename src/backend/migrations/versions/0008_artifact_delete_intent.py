"""Record durable artifact deletion intent for resumable deletes.

Revision ID: 0008_artifact_delete_intent
Revises: 0007_font_bundle
Create Date: 2026-11-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_artifact_delete_intent"
down_revision = "0007_font_bundle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("artifacts") as batch:
        batch.add_column(
            sa.Column("delete_requested_at", sa.String(64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("artifacts") as batch:
        batch.drop_column("delete_requested_at")
