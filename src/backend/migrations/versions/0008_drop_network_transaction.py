"""0008: Drop runtime network transaction state (t054).

The network configuration moved to deploy time (ADR 031): the HTTPS port
comes from the deployment environment, the Caddyfile is rendered once by
deploy.sh, and API + Gateway derive the Origin whitelist from the same
port. The runtime network transaction / pending / applied state that
lived as ``network.*`` rows in the ``settings`` table has no reader left
— the NetworkService, the Gateway publication protocol, the Supervisor
rebuild-edge / converge-streams endpoints, and the repository network
methods are all deleted in the same task — so the upgrade deletes every
such row.

Downgrade is a documented no-op, not a restore: the deleted rows have no
restore path by design (the code that would read them is gone), and the
migration test that walks the chain (test_control_migration.py) runs this
downgrade on its way back to the 0003 baseline — raising here would break
that walk without protecting any real data.
"""

from __future__ import annotations

from alembic import op

revision: str = "3751fed02a4a"
down_revision: str | None = "1a8db6b91744"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("DELETE FROM settings WHERE key LIKE 'network.%'")


def downgrade() -> None:
    # No-op by design: deleted network.* rows have no restore path (see
    # the module docstring). The settings table keeps every other row.
    return None
