"""0005: stable human-readable Profile display number (t050).

Every Profile gets one deployment-local number (0001, 0002, ...) that is
assigned at creation and never reused or renumbered: it names the sandbox
containers, labels them, and is exposed by the API so the product UI and
Docker Desktop show the same identity.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b7c2d9e4f611"
down_revision: str | None = "0e2ab6553470"
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
    bind.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS profile_display_sequence ("
            "id INTEGER PRIMARY KEY, value INTEGER NOT NULL)"
        )
    )
    if "display_number" not in _existing_columns(bind, "profiles"):
        with op.batch_alter_table("profiles") as batch_op:
            batch_op.add_column(sa.Column("display_number", sa.Integer(), nullable=True))
    # Backfill deterministically by creation order, then enforce uniqueness.
    bind.execute(
        sa.text(
            """
            UPDATE profiles
               SET display_number = (
                    SELECT n FROM (
                        SELECT id AS pid,
                               ROW_NUMBER() OVER (ORDER BY created_at, id) AS n
                          FROM profiles
                    ) numbered
                    WHERE numbered.pid = profiles.id
               )
             WHERE display_number IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_profiles_display_number "
            "ON profiles(display_number)"
        )
    )
    bind.execute(
        sa.text(
            "INSERT OR IGNORE INTO profile_display_sequence (id, value) "
            "VALUES (1, 0)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE profile_display_sequence SET value = "
            "COALESCE((SELECT MAX(display_number) FROM profiles), 0) "
            "WHERE id = 1"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP TABLE IF EXISTS profile_display_sequence"))
    bind.execute(sa.text("DROP INDEX IF EXISTS uq_profiles_display_number"))
    if "display_number" in _existing_columns(bind, "profiles"):
        with op.batch_alter_table("profiles") as batch_op:
            batch_op.drop_column("display_number")
