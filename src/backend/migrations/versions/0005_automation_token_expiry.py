"""Add optional automation token expiry.

Revision ID: 0005_token_expiry
Revises: 0004_remove_modes
Create Date: 2026-11-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_token_expiry"
down_revision = "0004_remove_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("automation_tokens") as batch:
        batch.add_column(sa.Column("expires_at", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("automation_tokens") as batch:
        batch.drop_column("expires_at")
