"""0010: proxy egress observations gain country/city/latency (t074).

Adds the fields the UI needs for the country / city / status columns and
for a real network round-trip latency: ``country_name``, ``city`` and
``latency_ms``. All are nullable so existing rows stay valid; current-ness
is still computed from endpoint fingerprint / credential revision / TTL
in ``cbrowser.domain.egress_observation``.

Downgrade is unsupported (t056 A60): migrations only move forward; roll
back with a release rollback + data-directory rebuild instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "8c3f1d0a7b92"
down_revision: str | None = "796adb0bf159"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    with op.batch_alter_table("proxy_egress_observations") as batch_op:
        batch_op.add_column(sa.Column("country_name", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("city", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
