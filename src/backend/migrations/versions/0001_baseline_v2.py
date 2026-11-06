"""CBrowser v2 baseline schema (t035).

Single baseline revision replacing the 0001-0009 chain.  The revision id
is deliberately new: any database stamped with an old revision belongs to
a different schema generation and must be rebuilt, never upgraded in place.

Revision ID: b7e1c9d4a2f3
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1c9d4a2f3"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BASELINE_REVISION = revision


def upgrade() -> None:
    op.create_table(
        "profile_groups",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("color", sa.String(length=32), nullable=False, server_default="slate"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
    op.create_table(
        "proxies",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("scheme", sa.String(length=16), nullable=False),
        sa.Column("host", sa.String(length=512), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("password", sa.Text(), nullable=True),
        sa.Column("credential_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("region_label", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("fingerprint_seed", sa.Integer(), nullable=False),
        sa.Column(
            "group_id",
            sa.String(length=64),
            sa.ForeignKey("profile_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "proxy_id",
            sa.String(length=64),
            sa.ForeignKey("proxies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("locale", sa.String(length=64), nullable=True),
        sa.Column("screen_width", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("screen_height", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("gpu_family", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("humanize", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("human_preset", sa.String(length=32), nullable=False, server_default="default"),
        sa.Column("geoip", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("clipboard_sync", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("auto_launch", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("color_scheme", sa.String(length=32), nullable=True),
        sa.Column("font_bundle", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("launch_args", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("extension_paths", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("allow_3p_cookies", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("set_google_default", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("capture_preview", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("restore_session", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("transparent_proxy", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("portable_cookies", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_data_dir", sa.String(length=1024), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
    op.create_index("idx_profiles_group_id", "profiles", ["group_id"])
    op.create_index("idx_profiles_proxy_id", "profiles", ["proxy_id"])
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
    op.create_table(
        "profile_runtimes",
        sa.Column(
            "profile_id",
            sa.String(length=64),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("desired_state", sa.String(length=32), nullable=False, server_default="stopped"),
        sa.Column("observed_state", sa.String(length=32), nullable=False, server_default="stopped"),
        sa.Column("runtime_instance_id", sa.String(length=128), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("restart_blocked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("last_exit_event_id", sa.String(length=128), nullable=True),
        sa.Column("last_started_at", sa.String(length=64), nullable=True),
        sa.Column("last_stopped_at", sa.String(length=64), nullable=True),
        sa.Column("browser_product", sa.String(length=255), nullable=True),
        sa.Column("browser_user_agent", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
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
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="upload"),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("picker_name", sa.String(length=255), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("storage_path", sa.String(length=4096), nullable=True),
        sa.Column("delete_requested_at", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
    )
    op.create_index("idx_artifacts_profile_id", "artifacts", ["profile_id"])
    op.create_index("idx_artifacts_profile_sha256", "artifacts", ["profile_id", "sha256"])
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
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
        sa.Column("event_type", sa.String(length=64), nullable=False, server_default="exit"),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("exit_reason", sa.String(length=255), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
    )
    op.create_index("idx_runtime_events_profile", "runtime_events", ["profile_id"])
    op.create_index("idx_runtime_events_instance", "runtime_events", ["runtime_instance_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("details", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
    )
    op.create_table(
        "admins",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
    )
    op.create_index("idx_sessions_token_hash", "sessions", ["token_hash"])
    op.create_table(
        "automation_tokens",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("profile_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("revoked_at", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.String(length=64), nullable=True),
    )
    op.create_index("idx_automation_tokens_token_hash", "automation_tokens", ["token_hash"])
    op.create_table(
        "profile_controls",
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("owner", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent_instance_id", sa.String(length=128), nullable=True),
        sa.Column("agent_session_id", sa.String(length=128), nullable=True),
        sa.Column("handoff_reason", sa.String(length=64), nullable=True),
        sa.Column("handoff_detail", sa.String(length=256), nullable=True),
        sa.Column("agent_reclaim_allowed", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("pending_supervisor_close", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id"),
    )


def downgrade() -> None:
    for name in (
        "profile_controls", "automation_tokens", "sessions", "admins",
        "audit_events", "runtime_events", "settings", "artifacts",
        "profile_runtimes", "profile_config_versions", "profiles",
        "proxies", "profile_groups",
    ):
        op.drop_table(name)
