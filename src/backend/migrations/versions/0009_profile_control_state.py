"""Add per-profile human-priority control state (t031, ADR 019).

Revision ID: 0009_profile_control_state
Revises: 0008_artifact_delete_intent
Create Date: 2026-11-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_profile_control_state"
down_revision = "0008_artifact_delete_intent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_controls",
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("owner", sa.String(16), nullable=False, server_default="user"),
        sa.Column("generation", sa.Integer, nullable=False, server_default="0"),
        sa.Column("agent_instance_id", sa.String(128), nullable=True),
        sa.Column("agent_session_id", sa.String(128), nullable=True),
        sa.Column("handoff_reason", sa.String(64), nullable=True),
        sa.Column("handoff_detail", sa.String(256), nullable=True),
        sa.Column(
            "agent_reclaim_allowed", sa.Boolean, nullable=False, server_default="1"
        ),
        sa.Column(
            "pending_supervisor_close", sa.Boolean, nullable=False, server_default="0"
        ),
        sa.Column("updated_at", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("profile_id"),
    )


def downgrade() -> None:
    op.drop_table("profile_controls")
