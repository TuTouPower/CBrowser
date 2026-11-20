"""0015: durable server-side egress probe jobs (t094).

Replaces the client-side serial probe loop and synchronous `/probe` with a
server-owned async job: a frozen target set, a durable job with per-member
state, and counts for an authoritative read model across refreshes and
restarts. The existing observation table remains the per-item result store.

Downgrade is unsupported: cbrowser migrations only move forward.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e89a0014c001"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    op.create_table(
        "proxy_probe_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="running"),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("kind", sa.String(32), nullable=False, server_default="probe"),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(64), nullable=False),
    )
    op.create_index("idx_proxy_probe_jobs_state", "proxy_probe_jobs", ["state"])
    op.create_table(
        "proxy_probe_job_members",
        sa.Column("job_id", sa.String(64), sa.ForeignKey("proxy_probe_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("proxy_id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("observation_at", sa.String(64), nullable=True),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index(
        "idx_proxy_probe_job_members_job", "proxy_probe_job_members", ["job_id"]
    )


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
