"""0012 (branch numbering): separate deletion batch membership from the intent (p130/p136).

Rechained on main after t083 ``0013_runtime_state_revision``
(``d83a2c12b083``) and t075 ``0013_profile_identity`` (``d75a0013f001``);
logically 0015. The revision id is unchanged.

A durable deletion intent can be confirmed from more than one client at
once. Membership used to be a single ``batch_id`` column on the intent,
so the later confirmation moved the intent to its own batch and the
first client's poll returned an empty set / 404 (p130). Store membership
as rows instead so every confirming batch observes the same intent.
A late request can then also re-join an already-finished intent instead
of creating a spurious ``profile_not_found`` intent (p136).

Downgrade is unsupported: cbrowser migrations only move forward.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d7e3a91f4c62"
down_revision: str | None = "d75a0013f001"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    op.create_table(
        "profile_deletion_batch_members",
        sa.Column("batch_id", sa.String(64), primary_key=True),
        sa.Column("operation_id", sa.String(64), primary_key=True),
    )
    op.create_index(
        "idx_deletion_batch_members_operation",
        "profile_deletion_batch_members",
        ["operation_id"],
    )
    op.execute(
        "INSERT INTO profile_deletion_batch_members (batch_id, operation_id) "
        "SELECT batch_id, id FROM profile_deletions"
    )


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
