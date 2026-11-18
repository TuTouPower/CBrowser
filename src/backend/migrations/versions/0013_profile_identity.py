"""0013: profile runtime identity unification (t075).

The profile configuration converges to one identity shape:

- ``gpu_family`` is dropped.  The fixed engine derives GPU identity
  from the persistent fingerprint seed + platform (spike s026); the old
  ``nvidia`` / ``intel`` values forced a raw Chromium flag that nothing
  validated, so they have no equivalent under the new contract.
- ``color_scheme`` becomes exactly ``light`` / ``dark``, NOT NULL,
  default ``light``.  Legacy NULL and ``no-preference`` rows are
  backfilled to ``light`` — the fixed engine measured both as light
  (p124), so the mapping is evidence-backed, not a guess.
- ``include_cjk_fonts`` is added (NOT NULL, default on).  Backfill
  preserves the *effective* exposure of the abolished locale rule: the
  old fontconfig rejected Chinese fonts only for ``locale='en-US'``,
  so en-US rows get 0 and every other row (including NULL locale,
  which was never rejected) gets 1.
- Unbound profiles (``font_set_id`` NULL) are bound to their platform's
  catalog default: the most recently verified ``font_set_assets`` row
  (ties broken by set_id), the same rule the service applies.
- ``profile_config_versions`` snapshots are rewritten to the same
  shape (gpu key removed, color scheme mapped, CJK flag derived,
  unbound snapshots bound), so historical versions stay readable
  under the new domain model.

Fail-before-write guard: the upgrade first computes every entry that
cannot be mapped equivalently — a forced GPU vendor, a binding that
is not a verified set for its platform, or an unbound profile whose
platform has no verified set at all.  The same guard scans
``profile_config_versions`` snapshots (corrupt JSON included): a
version that cannot be mapped would come back unbound, dangling or
GPU-forced on restore, so it blocks the upgrade with the profiles
instead of being silently rewritten or left behind.  If any entry
exists, the upgrade raises with the full list and writes nothing;
resolve those profiles (or import/verify the missing font sets) and
re-run.  Backup/restore is the deployment-level drill: take a file
copy of the database before upgrading; restoring the copy restores
the old shape wholesale, because this migration never touches
browser user data.

Downgrade is unsupported (t056 A60): migrations only move forward;
roll back with a release rollback + data-directory rebuild instead.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision: str = "d75a0013f001"
down_revision: str | None = "c81f0a11b001"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def _platform_defaults(conn) -> dict[str, str]:
    """Catalog default per platform: most recently verified set."""
    rows = conn.execute(
        sa.text(
            "SELECT platform, set_id, verified_at, created_at "
            "FROM font_set_assets WHERE state = 'verified'"
        )
    ).fetchall()
    by_platform: dict[str, list[tuple[str, str, str]]] = {}
    for platform, set_id, verified_at, created_at in rows:
        by_platform.setdefault(platform, []).append(
            (verified_at or created_at, set_id, set_id)
        )
    defaults: dict[str, str] = {}
    for platform, candidates in by_platform.items():
        candidates.sort(key=lambda item: (item[0], item[1]))
        defaults[platform] = candidates[-1][2]
    return defaults


def _blocking_entries(conn, defaults: dict[str, str]) -> list[str]:
    entries: list[str] = []
    forced = conn.execute(
        sa.text(
            "SELECT id, gpu_family FROM profiles "
            "WHERE gpu_family IS NOT NULL AND gpu_family <> 'auto'"
        )
    ).fetchall()
    for profile_id, gpu_family in forced:
        entries.append(
            f"profile {profile_id}: gpu_family={gpu_family!r} forces a GPU "
            "vendor, which has no equivalent under the t075 auto policy"
        )
    verified = {
        (platform, set_id)
        for platform, set_id in conn.execute(
            sa.text(
                "SELECT platform, set_id FROM font_set_assets "
                "WHERE state = 'verified'"
            )
        ).fetchall()
    }
    profiles = conn.execute(
        sa.text("SELECT id, fingerprint_platform, font_set_id FROM profiles")
    ).fetchall()
    for profile_id, platform, font_set_id in profiles:
        if font_set_id:
            if (platform, font_set_id) not in verified:
                entries.append(
                    f"profile {profile_id}: font_set_id {font_set_id!r} is "
                    f"not a verified {platform} font set"
                )
        elif platform not in defaults:
            entries.append(
                f"profile {profile_id}: no font set bound and no verified "
                f"{platform} font set exists to bind"
            )
    # Snapshots are readable history, not dead text: a version that
    # cannot be mapped equivalently would come back unbound, dangling
    # or GPU-forced on restore, so the same rules block the upgrade.
    snapshots = conn.execute(
        sa.text("SELECT id, profile_id, snapshot FROM profile_config_versions")
    ).fetchall()
    for row_id, profile_id, raw in snapshots:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            entries.append(
                f"snapshot {row_id} (profile {profile_id}): snapshot JSON "
                "is corrupt and cannot be rewritten to the new shape"
            )
            continue
        if not isinstance(data, dict):
            entries.append(
                f"snapshot {row_id} (profile {profile_id}): snapshot JSON "
                "is not an object and cannot be rewritten to the new shape"
            )
            continue
        gpu = data.get("gpu_family")
        if gpu is not None and gpu != "auto":
            entries.append(
                f"snapshot {row_id} (profile {profile_id}): gpu_family={gpu!r} "
                "forces a GPU vendor, which has no equivalent under the "
                "t075 auto policy"
            )
        snap_platform = data.get("fingerprint_platform") or "windows"
        snap_set = data.get("font_set_id")
        if snap_set:
            if (snap_platform, snap_set) not in verified:
                entries.append(
                    f"snapshot {row_id} (profile {profile_id}): font_set_id "
                    f"{snap_set!r} is not a verified {snap_platform} font set"
                )
        elif snap_platform not in defaults:
            entries.append(
                f"snapshot {row_id} (profile {profile_id}): no font set "
                f"bound and no verified {snap_platform} font set exists "
                "to bind"
            )
    return entries


def _rewrite_snapshots(conn, defaults: dict[str, str]) -> None:
    rows = conn.execute(
        sa.text("SELECT id, snapshot FROM profile_config_versions")
    ).fetchall()
    for row_id, raw in rows:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        data.pop("gpu_family", None)
        if data.get("color_scheme") in (None, "no-preference"):
            data["color_scheme"] = "light"
        if "include_cjk_fonts" not in data:
            # Same effective-exposure rule as the column backfill: the
            # old fontconfig rejected Chinese fonts only for en-US.
            data["include_cjk_fonts"] = data.get("locale") != "en-US"
        if not data.get("font_set_id"):
            platform = data.get("fingerprint_platform") or "windows"
            if platform in defaults:
                data["font_set_id"] = defaults[platform]
        rewritten = json.dumps(data, ensure_ascii=False)
        if rewritten != raw:
            conn.execute(
                sa.text(
                    "UPDATE profile_config_versions SET snapshot = :snapshot "
                    "WHERE id = :row_id"
                ),
                {"snapshot": rewritten, "row_id": row_id},
            )


def upgrade() -> None:
    conn = op.get_bind()
    defaults = _platform_defaults(conn)
    blocking = _blocking_entries(conn, defaults)
    if blocking:
        raise RuntimeError(
            "t075 identity migration blocked; nothing was written. "
            "Resolve these entries and re-run:\n" + "\n".join(blocking)
        )

    conn.execute(
        sa.text(
            "UPDATE profiles SET color_scheme = 'light' "
            "WHERE color_scheme IS NULL OR color_scheme = 'no-preference'"
        )
    )
    with op.batch_alter_table("profiles", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("include_cjk_fonts", sa.Boolean(), nullable=True)
        )
        batch_op.drop_column("gpu_family")
        batch_op.alter_column(
            "color_scheme",
            existing_type=sa.String(32),
            nullable=False,
            server_default="light",
        )
    conn.execute(
        sa.text(
            "UPDATE profiles SET include_cjk_fonts = "
            "CASE WHEN locale = 'en-US' THEN 0 ELSE 1 END"
        )
    )
    with op.batch_alter_table("profiles", recreate="always") as batch_op:
        batch_op.alter_column(
            "include_cjk_fonts",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default="1",
        )
    for platform, set_id in defaults.items():
        conn.execute(
            sa.text(
                "UPDATE profiles SET font_set_id = :set_id "
                "WHERE font_set_id IS NULL AND fingerprint_platform = :platform"
            ),
            {"set_id": set_id, "platform": platform},
        )
    _rewrite_snapshots(conn, defaults)


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
