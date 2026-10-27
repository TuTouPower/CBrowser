"""initial schema with 8 core tables

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. profiles table
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("fingerprint_seed", sa.Integer(), nullable=False),
        sa.Column("proxy", sa.String(length=512), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("locale", sa.String(length=64), nullable=True),
        sa.Column("screen_width", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("screen_height", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column(
            "gpu_family", sa.String(length=32), nullable=False, server_default="auto"
        ),
        sa.Column("humanize", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "human_preset",
            sa.String(length=32),
            nullable=False,
            server_default="default",
        ),
        sa.Column("geoip", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("clipboard_sync", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("auto_launch", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("color_scheme", sa.String(length=32), nullable=True),
        sa.Column("launch_args", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("extension_paths", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("allow_3p_cookies", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "set_google_default", sa.Boolean(), nullable=False, server_default="1"
        ),
        sa.Column("capture_preview", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("restore_session", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "transparent_proxy", sa.Boolean(), nullable=False, server_default="0"
        ),
        sa.Column("portable_cookies", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_data_dir", sa.String(length=1024), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "runtime_mode",
            sa.String(length=32),
            nullable=False,
            server_default="docker",
        ),
        sa.Column(
            "viewer_mode", sa.String(length=32), nullable=False, server_default="webrtc"
        ),
        sa.Column(
            "current_config_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )

    # 2. profile_config_versions table
    op.create_table(
        "profile_config_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(length=64),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("profile_id", "version", name="uq_profile_version"),
    )

    # 3. profile_tags table
    op.create_table(
        "profile_tags",
        sa.Column(
            "profile_id",
            sa.String(length=64),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tag", sa.String(length=64), primary_key=True),
        sa.Column("color", sa.String(length=32), nullable=True),
    )

    # 4. profile_runtimes table
    op.create_table(
        "profile_runtimes",
        sa.Column(
            "profile_id",
            sa.String(length=64),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "desired_state",
            sa.String(length=32),
            nullable=False,
            server_default="stopped",
        ),
        sa.Column(
            "observed_state",
            sa.String(length=32),
            nullable=False,
            server_default="stopped",
        ),
        sa.Column("runtime_instance_id", sa.String(length=128), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("restart_blocked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("last_exit_event_id", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )

    # 5. artifacts table
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(length=64),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "kind", sa.String(length=32), nullable=False, server_default="upload"
        ),
        sa.Column(
            "state", sa.String(length=32), nullable=False, server_default="ready"
        ),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("picker_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
    )
    op.create_index("idx_artifacts_profile_id", "artifacts", ["profile_id"])

    # 6. settings table
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )

    # 7. runtime_events table
    op.create_table(
        "runtime_events",
        sa.Column("event_id", sa.String(length=128), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(length=64),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("runtime_instance_id", sa.String(length=128), nullable=False),
        sa.Column(
            "event_type", sa.String(length=64), nullable=False, server_default="exit"
        ),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("exit_reason", sa.String(length=255), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
    )
    op.create_index("idx_runtime_events_profile", "runtime_events", ["profile_id"])
    op.create_index(
        "idx_runtime_events_instance", "runtime_events", ["runtime_instance_id"]
    )

    # 8. audit_events table
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column(
            "actor", sa.String(length=64), nullable=False, server_default="system"
        ),
        sa.Column("details", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("runtime_events")
    op.drop_table("settings")
    op.drop_table("artifacts")
    op.drop_table("profile_runtimes")
    op.drop_table("profile_tags")
    op.drop_table("profile_config_versions")
    op.drop_table("profiles")
