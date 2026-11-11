"""0006: proxy egress observations; drop writable country_code (t052).

``proxies.country_code`` was a writable static configuration; the country
is now an *observation* of the proxy's egress IP (Browser perspective),
stored in ``proxy_egress_observations`` with the endpoint fingerprint and
credential revision it was measured against.  Old values are not imported
(no real users, no data migration).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c8d3e7a1f904"
down_revision: str | None = "b7c2d9e4f611"
branch_labels: str | None = None
depends_on: str | None = None


def _existing_columns(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    try:
        return {col["name"] for col in insp.get_columns(table_name)}
    except sa.exc.NoSuchTableError:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("proxy_egress_observations"):
        op.create_table(
            "proxy_egress_observations",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column(
                "proxy_id",
                sa.String(64),
                sa.ForeignKey("proxies.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("endpoint_fingerprint", sa.String(64), nullable=False),
            sa.Column("credential_revision", sa.Integer, nullable=False),
            sa.Column(
                "perspective",
                sa.String(32),
                nullable=False,
                server_default="browser",
            ),
            sa.Column("egress_ip", sa.String(64), nullable=True),
            sa.Column("country_code", sa.String(2), nullable=True),
            sa.Column(
                "source",
                sa.String(64),
                nullable=False,
                server_default="supervisor_probe",
            ),
            sa.Column(
                "status", sa.String(16), nullable=False, server_default="pending"
            ),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("observed_at", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.String(64), nullable=True),
            sa.Column("created_at", sa.String(64), nullable=False),
        )
        op.create_index(
            "idx_proxy_egress_observations_proxy_id",
            "proxy_egress_observations",
            ["proxy_id"],
        )
    if "country_code" in _existing_columns(bind, "proxies"):
        with op.batch_alter_table("proxies") as batch_op:
            batch_op.drop_column("country_code")


_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: CBrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
