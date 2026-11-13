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

Downgrade is unsupported (t056 A60): migrations only move forward, and
the deleted rows have no restore path by design (the code that would read
them is gone). Roll back with a release rollback and a data-directory
rebuild instead.
"""

from __future__ import annotations

from alembic import op

revision: str = "3751fed02a4a"
down_revision: str | None = "1a8db6b91744"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: CBrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    op.execute("DELETE FROM settings WHERE key LIKE 'network.%'")


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
