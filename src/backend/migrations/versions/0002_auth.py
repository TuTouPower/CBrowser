"""Add auth tables: admins, sessions, automation_tokens

Revision ID: 0002_auth
Revises: 0001_initial_schema
Create Date: 2026-10-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_auth"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. admins table
    op.create_table(
        "admins",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )

    # 2. sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
    )
    op.create_index("idx_sessions_token_hash", "sessions", ["token_hash"])

    # 3. automation_tokens table
    op.create_table(
        "automation_tokens",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("profile_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("revoked_at", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "idx_automation_tokens_token_hash", "automation_tokens", ["token_hash"]
    )


def downgrade() -> None:
    op.drop_table("automation_tokens")
    op.drop_table("sessions")
    op.drop_table("admins")
