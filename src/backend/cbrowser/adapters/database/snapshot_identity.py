"""Shared snapshot identity validation and rewrite helpers for 0013 / 0014 migrations.

Supports both historical flat snapshots and production wrapped snapshots
(``{"config": <profile_config_dict>, "proxy_credential_revision": ...}``).
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

WRAPPED_SPURIOUS_OUTER_KEYS: tuple[str, ...] = (
    "gpu_family",
    "color_scheme",
    "include_cjk_fonts",
    "font_set_id",
)


def load_verified_catalog(conn: Any) -> tuple[set[tuple[str, str]], dict[str, str]]:
    """Return ``(verified_pairs, platform_defaults)`` from ``font_set_assets``."""
    rows = conn.execute(
        sa.text(
            "SELECT platform, set_id, verified_at, created_at "
            "FROM font_set_assets WHERE state = 'verified'"
        )
    ).fetchall()
    verified: set[tuple[str, str]] = set()
    by_platform: dict[str, list[tuple[str, str]]] = {}
    for platform, set_id, verified_at, created_at in rows:
        verified.add((platform, set_id))
        by_platform.setdefault(platform, []).append(
            (verified_at or created_at or "", set_id)
        )
    defaults: dict[str, str] = {}
    for platform, candidates in by_platform.items():
        candidates.sort(key=lambda item: (item[0], item[1]))
        defaults[platform] = candidates[-1][1]
    return verified, defaults


def _unpack_snapshot(
    raw: Any,
    row_id: str,
    profile_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    """Decode raw snapshot JSON and return ``(outer_dict, config_dict, error)``."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return (
            None,
            None,
            f"snapshot {row_id} (profile {profile_id}): snapshot JSON "
            "is corrupt and cannot be rewritten to the new shape",
        )
    if not isinstance(data, dict):
        return (
            None,
            None,
            f"snapshot {row_id} (profile {profile_id}): snapshot JSON "
            "is not an object and cannot be rewritten to the new shape",
        )
    if "config" in data:
        cfg = data["config"]
        if not isinstance(cfg, dict):
            return (
                None,
                None,
                f"snapshot {row_id} (profile {profile_id}): snapshot "
                "nested config is not an object and cannot be rewritten to the new shape",
            )
        return data, cfg, None
    return data, data, None


def _snapshot_needs_migration(data: dict[str, Any], cfg: dict[str, Any]) -> bool:
    """Return True when a snapshot still holds legacy or outer-polluted fields."""
    if "config" in data and any(key in data for key in WRAPPED_SPURIOUS_OUTER_KEYS):
        return True
    if "gpu_family" in cfg:
        return True
    if cfg.get("color_scheme") in (None, "no-preference"):
        return True
    return not isinstance(cfg.get("include_cjk_fonts"), bool)


def _check_font_set_binding(
    row_id: str,
    profile_id: str,
    cfg: dict[str, Any],
    verified: set[tuple[str, str]],
    defaults: dict[str, str],
) -> str | None:
    """Validate that an unmigrated snapshot resolves to a verified font set."""
    snap_platform = cfg.get("fingerprint_platform") or "windows"
    snap_set = cfg.get("font_set_id")
    if snap_set:
        if (snap_platform, snap_set) not in verified:
            return (
                f"snapshot {row_id} (profile {profile_id}): font_set_id "
                f"{snap_set!r} is not a verified {snap_platform} font set"
            )
        return None
    if snap_platform not in defaults:
        return (
            f"snapshot {row_id} (profile {profile_id}): no font set "
            f"bound and no verified {snap_platform} font set exists "
            "to bind"
        )
    return None


def find_blocking_snapshot_entries(
    conn: Any,
    verified: set[tuple[str, str]],
    defaults: dict[str, str],
    *,
    skip_clean: bool = False,
) -> list[str]:
    """Inspect config-version snapshots and list any that cannot map safely."""
    entries: list[str] = []
    snapshots = conn.execute(
        sa.text("SELECT id, profile_id, snapshot FROM profile_config_versions")
    ).fetchall()
    for row_id, profile_id, raw in snapshots:
        data, cfg, err = _unpack_snapshot(raw, row_id, profile_id)
        if err is not None or data is None or cfg is None:
            if err is not None:
                entries.append(err)
            continue

        gpu = cfg.get("gpu_family")
        if gpu is not None and gpu != "auto":
            entries.append(
                f"snapshot {row_id} (profile {profile_id}): gpu_family={gpu!r} "
                "forces a GPU vendor, which has no equivalent under the "
                "t075 auto policy"
            )
        if skip_clean and not _snapshot_needs_migration(data, cfg):
            continue

        font_err = _check_font_set_binding(row_id, profile_id, cfg, verified, defaults)
        if font_err is not None:
            entries.append(font_err)
    return entries


def rewrite_profile_config_snapshots(
    conn: Any,
    defaults: dict[str, str],
    *,
    strip_wrapped_outer: bool = True,
    skip_clean: bool = False,
) -> None:
    """Upgrade flat or wrapped snapshots in place without altering wrapper metadata."""
    rows = conn.execute(
        sa.text("SELECT id, profile_id, snapshot FROM profile_config_versions")
    ).fetchall()
    for row_id, profile_id, raw in rows:
        data, cfg, err = _unpack_snapshot(raw, row_id, profile_id)
        if err is not None or data is None or cfg is None:
            continue
        if skip_clean and not _snapshot_needs_migration(data, cfg):
            continue
        if "config" in data and strip_wrapped_outer:
            for outer_key in WRAPPED_SPURIOUS_OUTER_KEYS:
                data.pop(outer_key, None)

        cfg.pop("gpu_family", None)
        if cfg.get("color_scheme") in (None, "no-preference"):
            cfg["color_scheme"] = "light"
        if "include_cjk_fonts" not in cfg:
            # Same effective-exposure rule as the column backfill: the
            # old fontconfig rejected Chinese fonts only for en-US.
            cfg["include_cjk_fonts"] = cfg.get("locale") != "en-US"
        if not cfg.get("font_set_id"):
            platform = cfg.get("fingerprint_platform") or "windows"
            if platform in defaults:
                cfg["font_set_id"] = defaults[platform]

        rewritten = json.dumps(data, ensure_ascii=False)
        if rewritten != raw:
            conn.execute(
                sa.text(
                    "UPDATE profile_config_versions SET snapshot = :snapshot "
                    "WHERE id = :row_id"
                ),
                {"snapshot": rewritten, "row_id": row_id},
            )
