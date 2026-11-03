#!/usr/bin/env python3
"""Migrate legacy CloakBrowser-Manager data root into v2 layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tarfile
import time
from pathlib import Path

from cbrowser.adapters.database.migrations import run_database_migrations

PROFILE_FIELDS = (
    "id name fingerprint_seed proxy timezone locale screen_width screen_height "
    "gpu_family humanize human_preset geoip clipboard_sync auto_launch color_scheme "
    "launch_args extension_paths allow_3p_cookies set_google_default capture_preview "
    "restore_session transparent_proxy portable_cookies notes user_data_dir created_at "
    "updated_at sort_order"
).split()


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def legacy_db(source: Path) -> Path:
    for name in ("profiles.db", "cbrowser.db"):
        path = source / name
        if path.is_file() and path.stat().st_size:
            return path
    raise SystemExit(f"No legacy database found under {source}")


def counts(db: Path) -> dict[str, int]:
    with connect(db) as conn:
        return {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("profiles", "profile_tags", "artifacts")
        }


def backup(source: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"legacy-{time.strftime('%Y%m%dT%H%M%S')}.tar.gz"
    with tarfile.open(target, "w:gz") as archive:
        archive.add(source, arcname=source.name)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (target.with_suffix(target.suffix + ".sha256")).write_text(digest + "\n")
    return target


def migrate(source: Path, target: Path, *, dry_run: bool) -> None:
    db_path = legacy_db(source)
    summary = counts(db_path)
    print(f"legacy_db={db_path}")
    print(f"profiles={summary['profiles']} tags={summary['profile_tags']} artifacts={summary['artifacts']}")
    if dry_run:
        with connect(db_path) as conn:
            for row in conn.execute("SELECT id, name, user_data_dir FROM profiles ORDER BY sort_order, created_at"):
                print(f"  {row['id']} {row['name']!r} data={row['user_data_dir']}")
        return

    for name in ("profiles", "artifacts", "runtime-events", "settings"):
        (target / name).mkdir(parents=True, exist_ok=True)
    v2_db = target / "cbrowser.db"
    if v2_db.exists() and counts(v2_db)["profiles"]:
        raise SystemExit("Target database already contains profiles; refusing in-place migration")
    run_database_migrations(v2_db)

    with connect(db_path) as old, connect(v2_db) as new:
        for row in old.execute("SELECT * FROM profiles ORDER BY sort_order, created_at"):
            values = {field: row[field] for field in PROFILE_FIELDS}
            profile_dir = target / "profiles" / row["id"] / "profile"
            profile_dir.parent.mkdir(parents=True, exist_ok=True)
            legacy_profile = source / "profiles" / row["id"]
            if not legacy_profile.is_dir():
                legacy_profile = Path(row["user_data_dir"])
                if not legacy_profile.is_absolute():
                    legacy_profile = source / legacy_profile
            if legacy_profile.is_dir():
                shutil.copytree(legacy_profile, profile_dir, dirs_exist_ok=True, symlinks=True, ignore_dangling_symlinks=True)
            values["user_data_dir"] = f"/data/profiles/{row['id']}/profile"
            values["current_config_version"] = 1
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            new.execute(f"INSERT INTO profiles ({columns}) VALUES ({placeholders})", tuple(values.values()))
            snapshot = {k: values[k] for k in values if k not in {"id", "created_at", "updated_at", "user_data_dir", "current_config_version"}}
            snapshot["humanize"] = bool(snapshot["humanize"])
            snapshot["geoip"] = bool(snapshot["geoip"])
            snapshot["clipboard_sync"] = bool(snapshot["clipboard_sync"])
            snapshot["auto_launch"] = bool(snapshot["auto_launch"])
            snapshot["allow_3p_cookies"] = bool(snapshot["allow_3p_cookies"])
            snapshot["set_google_default"] = bool(snapshot["set_google_default"])
            snapshot["capture_preview"] = bool(snapshot["capture_preview"])
            snapshot["restore_session"] = bool(snapshot["restore_session"])
            snapshot["transparent_proxy"] = bool(snapshot["transparent_proxy"])
            snapshot["portable_cookies"] = bool(snapshot["portable_cookies"])
            for field in ("launch_args", "extension_paths"):
                snapshot[field] = json.loads(snapshot[field] or "[]")
            tags = [dict(tag) for tag in old.execute("SELECT tag, color FROM profile_tags WHERE profile_id=?", (row["id"],))]
            new.execute(
                "INSERT INTO profile_config_versions (id, profile_id, version, snapshot, created_at) VALUES (?, ?, 1, ?, ?)",
                (f"{row['id']}:1", row["id"], json.dumps({"config": snapshot, "tags": tags}), row["created_at"]),
            )
            for tag in tags:
                new.execute("INSERT INTO profile_tags (profile_id, tag, color) VALUES (?, ?, ?)", (row["id"], tag["tag"], tag["color"]))
            for artifact in old.execute("SELECT * FROM artifacts WHERE profile_id=?", (row["id"],)):
                new.execute(
                    "INSERT INTO artifacts (id, profile_id, name, size, kind, state, content_type, picker_name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (artifact["id"], artifact["profile_id"], artifact["name"], artifact["size"], artifact["kind"], artifact["state"], artifact["content_type"], artifact["picker_name"], artifact["created_at"]),
                )
                legacy_art = source / "artifacts" / artifact["profile_id"]
                target_art = target / "artifacts" / artifact["profile_id"]
                if legacy_art.is_dir():
                    shutil.copytree(legacy_art, target_art, dirs_exist_ok=True)
        new.commit()
    print("migration complete")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, default=Path("data/backups"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.dry_run == args.apply:
        raise SystemExit("choose exactly one of --dry-run or --apply")
    if not args.source.is_dir():
        raise SystemExit(f"source not found: {args.source}")
    if args.dry_run:
        migrate(args.source, args.target, dry_run=True)
        return
    archive = backup(args.source, args.backup_dir)
    print(f"backup={archive}")
    migrate(args.source, args.target, dry_run=False)


if __name__ == "__main__":
    main()
