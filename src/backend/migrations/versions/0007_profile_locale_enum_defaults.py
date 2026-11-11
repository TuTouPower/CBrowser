"""0007: Profile locale enum and new advanced-option defaults (t053).

- ``profiles.locale`` is constrained to ``zh-CN`` / ``en-US`` (or NULL for
  legacy rows): the language field converges to the two-value enum, and
  the database rejects anything else even if it bypasses the API.
- ``humanize`` / ``portable_cookies`` server defaults flip from ``0`` to
  ``1`` to match the new domain, DTO and ORM defaults.

No stored values are rewritten: existing ``humanize`` / ``portable_cookies``
values stay as they are, and a pre-existing non-enum ``locale`` is left
untouched.  Such a row blocks this upgrade (the CHECK is validated while
the table is rebuilt), so clear or null out legacy locale values first;
there are no real users, only dev/test databases.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "1a8db6b91744"
down_revision: str | None = "c8d3e7a1f904"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("profiles", recreate="always") as batch_op:
        batch_op.alter_column(
            "humanize",
            existing_type=sa.Boolean(),
            server_default="1",
            existing_nullable=False,
        )
        batch_op.alter_column(
            "portable_cookies",
            existing_type=sa.Boolean(),
            server_default="1",
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_profiles_locale_enum",
            "locale IS NULL OR locale IN ('zh-CN', 'en-US')",
        )


_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: CBrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
