"""0014: idempotent compensation repair for wrapped profile config snapshots (t089).

Earlier ``0013_profile_identity.py`` treated the top-level JSON in
``profile_config_versions.snapshot`` as the config object, whereas repository
writes store ``{"config": <cfg>, "proxy_credential_revision": <rev>}``.
Databases already stamped at ``d7e3a91f4c62`` therefore still hold
``gpu_family`` / ``color_scheme=null`` / unbound ``font_set_id`` inside the
nested ``config`` object and spurious top-level keys alongside
``proxy_credential_revision``.

This forward-only compensation migration applies the exact same fail-before-write
check and idempotent transform to wrapped and flat snapshots alike, stripping
spurious outer wrapper keys while preserving ``proxy_credential_revision``.

Downgrade is unsupported: cbrowser migrations only move forward.
"""

from __future__ import annotations

from alembic import op

from cbrowser.adapters.database.snapshot_identity import (
    find_blocking_snapshot_entries,
    load_verified_catalog,
    rewrite_profile_config_snapshots,
)

revision: str = "e89a0014c001"
down_revision: str | None = "d7e3a91f4c62"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    conn = op.get_bind()
    verified, defaults = load_verified_catalog(conn)
    blocking = find_blocking_snapshot_entries(
        conn, verified, defaults, skip_clean=True
    )
    if blocking:
        raise RuntimeError(
            "t089 wrapped snapshot repair blocked; nothing was written. "
            "Resolve these entries and re-run:\n" + "\n".join(blocking)
        )
    rewrite_profile_config_snapshots(
        conn, defaults, strip_wrapped_outer=True, skip_clean=True
    )


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
