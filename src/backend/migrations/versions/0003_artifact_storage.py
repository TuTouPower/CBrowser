"""Add artifact checksum and canonical storage path

Revision ID: 0003_artifact_storage
Revises: 0002_auth
Create Date: 2026-11-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_artifact_storage"
down_revision: str | None = "0002_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("sha256", sa.String(length=64), nullable=True))
    op.add_column(
        "artifacts", sa.Column("storage_path", sa.String(length=4096), nullable=True)
    )
    op.create_index(
        "idx_artifacts_profile_sha256", "artifacts", ["profile_id", "sha256"]
    )


def downgrade() -> None:
    op.drop_index("idx_artifacts_profile_sha256", table_name="artifacts")
    op.drop_column("artifacts", "storage_path")
    op.drop_column("artifacts", "sha256")
