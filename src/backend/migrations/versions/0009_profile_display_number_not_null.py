"""0009: display_number becomes NOT NULL (t056, A21).

Every Profile row already carries a display number: 0005 backfilled all
pre-existing rows by creation order and every create path assigns the next
sequence value. The column was still nullable in the schema and the domain
models silently defaulted a missing number to 1, so a NULL could masquerade
as profile #0001. This revision closes the gap: any NULL left over is
backfilled first (same deterministic order as 0005), then the column is
altered to NOT NULL.

Downgrade is unsupported (t056 A60): migrations only move forward; roll
back with a release rollback + data-directory rebuild instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "796adb0bf159"
down_revision: str | None = "3751fed02a4a"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: CBrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    bind = op.get_bind()
    # Defensive backfill: 0005 already filled every NULL, but a NOT NULL
    # alter must never fail on a stray NULL row. Same deterministic order
    # as 0005 (creation order, then id).
    #
    # Only the NULL rows are numbered, offset by the existing maximum:
    # numbering ALL rows (as the first version of this revision did)
    # collides with surviving numbers wherever deletions left gaps
    # (e.g. rows at 1 and 3 plus one NULL row: the NULL row would be
    # assigned 3). The offset is read once, before the UPDATE, and the
    # numbering is computed once in the FROM clause: a correlated
    # subquery over the NULL subset would be re-evaluated per row while
    # the set of NULL rows shrinks, and mixing MAX() with ROW_NUMBER()
    # in one SELECT level is rejected by SQLite ("misuse of aggregate").
    max_number = bind.execute(
        sa.text("SELECT COALESCE(MAX(display_number), 0) FROM profiles")
    ).scalar()
    bind.execute(
        sa.text(
            """
            UPDATE profiles
               SET display_number = numbered.n + :offset
              FROM (
                    SELECT id AS pid,
                           ROW_NUMBER() OVER (ORDER BY created_at, id) AS n
                      FROM profiles
                     WHERE display_number IS NULL
                   ) AS numbered
             WHERE profiles.id = numbered.pid
            """
        ),
        {"offset": max_number},
    )
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.alter_column(
            "display_number",
            existing_type=sa.Integer(),
            nullable=False,
        )


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
