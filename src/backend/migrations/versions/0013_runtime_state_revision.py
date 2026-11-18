"""0013: profile runtime state revision (t083).

Adds ``profile_runtimes.state_revision``: a per-Profile monotonic
revision incremented on every runtime row update.  The Supervisor's
minimal batch state protocol fences snapshots and change notices with
it (together with the API process epoch), so a late or replayed notice
can never overwrite newer intent.

Downgrade is unsupported (t056 A60): migrations only move forward; roll
back with a release rollback + data-directory rebuild instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d83a2c12b083"
down_revision: str | None = "c81f0a11b001"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    op.add_column(
        "profile_runtimes",
        sa.Column(
            "state_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
