"""Remove obsolete runtime/viewer mode keys from stored config snapshots.

Revision ID: 0006_snapshot_modes
Revises: 0005_token_expiry
Create Date: 2026-11-03
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "0006_snapshot_modes"
down_revision = "0005_token_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, snapshot FROM profile_config_versions")
    ).fetchall()
    for row_id, raw in rows:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        config = data.get("config")
        if not isinstance(config, dict):
            continue
        changed = False
        for key in ("runtime_mode", "viewer_mode"):
            if key in config:
                config.pop(key)
                changed = True
        if changed:
            connection.execute(
                sa.text(
                    "UPDATE profile_config_versions SET snapshot = :snapshot "
                    "WHERE id = :id"
                ),
                {"snapshot": json.dumps(data), "id": row_id},
            )


def downgrade() -> None:
    # Removed keys were single-value constants; no data restoration is needed.
    pass
