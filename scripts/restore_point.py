#!/usr/bin/env python3
"""Environment restore points for CBrowser (t066).

One restore point is a *set*: the control-plane database (named volume)
plus every Profile's browser user data directory, captured at a single
quiescent moment, with a manifest that makes the set verifiable before
anything is allowed to overwrite live data.

    restore_point.py create  --db /db/cbrowser.db --data-root /data \
        --out /backups/point-20261113 [--secrets-dir /secrets] [--label x]
    restore_point.py verify  --point /backups/point-20261113
    restore_point.py restore --point /backups/point-20261113 \
        --db /db/cbrowser.db --data-root /data

Design rules (t066 AC-009/AC-010):

* ``create`` refuses while the database records any actual writer
  (desired running, a lifecycle transition, or a bound runtime
  instance).  The DB snapshot uses the SQLite online-backup API and
  must pass ``PRAGMA integrity_check`` before the point is published;
  the manifest records per-file SHA-256 digests, the schema stamp and
  each Profile's config version.  Credential material is never copied:
  the manifest lists credential *prerequisites* (file names and sizes
  only) that a restore site must provide separately.
* ``restore`` validates the whole point (hashes, DB integrity, schema
  stamp against the live database, free space) and stages copies next
  to their targets *before* any live byte moves.  The set switch is
  rename-based per item, journaled after every item: an interruption
  leaves either the complete old set or the complete new set in place,
  and the next ``restore`` invocation first rolls an interrupted switch
  back to the old set.  The pre-restore set is retained next to the
  targets (``.pre-restore-<switch-id>``) and named in the journal.
  The journal itself defaults to ``<data-root>/.restore-journal.json``
  — on the same persistent volume as the set it protects — unless
  ``--journal`` names another (equally persistent) location.
* ``restore`` expects the stack to be stopped (``deploy.sh env-restore``
  runs ``compose down`` first), the same precondition as db_restore.py.

Exit codes: 0 ok; 1 validation/usage failure; 2 writer refusal on
create; 3 an interrupted switch was rolled back (re-run to proceed).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

FORMAT_VERSION = 1
SKIP_NAMES = frozenset({"SingletonLock", "SingletonCookie", "SingletonSocket"})
TRANSITIONAL_STATES = ("starting", "running", "stopping")


class RestorePointError(Exception):
    """A validation or protocol failure; the message is operator-facing."""


class WriterActiveError(RestorePointError):
    """The database records an actual writer; creation must not proceed."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, payload: dict) -> None:
    temporary = path.parent / (uuid.uuid4().hex + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    _fsync_dir(path.parent)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(
        "file:" + quote(str(db_path)) + "?mode=ro", uri=True
    )


def _schema_stamp(db_path: Path) -> str | None:
    try:
        connection = _connect_ro(db_path)
    except sqlite3.DatabaseError:
        return None
    try:
        row = connection.execute(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
    except sqlite3.DatabaseError:
        return None
    finally:
        connection.close()
    return str(row[0]) if row else None


def _integrity_ok(db_path: Path) -> bool:
    try:
        connection = _connect_ro(db_path)
        try:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return False
    return row is not None and row[0] == "ok"


def read_writer_offenders(db_path: Path) -> list[str]:
    """Profile ids whose runtime rows trace an actual writer."""
    connection = _connect_ro(db_path)
    try:
        rows = connection.execute(
            "SELECT profile_id, desired_state, observed_state,"
            " runtime_instance_id FROM profile_runtimes"
        ).fetchall()
    finally:
        connection.close()
    offenders = []
    for profile_id, desired, observed, instance_id in rows:
        if (
            desired == "running"
            or observed in TRANSITIONAL_STATES
            or instance_id is not None
        ):
            offenders.append(str(profile_id))
    return sorted(offenders)


def read_profiles(db_path: Path) -> list[dict]:
    connection = _connect_ro(db_path)
    try:
        rows = connection.execute(
            "SELECT id, user_data_dir, current_config_version"
            " FROM profiles ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    return [
        {"id": str(r[0]), "user_data_dir": str(r[1]), "config_version": int(r[2])}
        for r in rows
    ]


def _copy_tree_manifest(source: Path, target: Path) -> dict[str, dict]:
    """Copy ``source`` into ``target`` recording a per-entry manifest.

    Singleton rendezvous files are skipped (they name a live process and
    are meaningless in a restore point), matching the profile clone.
    """
    entries: dict[str, dict] = {}
    target.mkdir(parents=True, exist_ok=True)
    for directory, dirnames, filenames in os.walk(source, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_NAMES)
        base = Path(directory)
        relative_dir = base.relative_to(source)
        (target / relative_dir).mkdir(parents=True, exist_ok=True)
        for name in dirnames:
            child = base / name
            if child.is_symlink():
                link_target = os.readlink(child)
                (target / relative_dir / name).symlink_to(link_target)
                entries[str(relative_dir / name)] = {"link": link_target}
        for name in sorted(filenames):
            if name in SKIP_NAMES:
                continue
            child = base / name
            relative = str(relative_dir / name)
            destination = target / relative_dir / name
            if child.is_symlink():
                link_target = os.readlink(child)
                destination.symlink_to(link_target)
                entries[relative] = {"link": link_target}
                continue
            digest = hashlib.sha256()
            size = 0
            with child.open("rb") as src, destination.open("wb") as dst:
                while chunk := src.read(1024 * 1024):
                    digest.update(chunk)
                    dst.write(chunk)
                    size += len(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            shutil.copymode(child, destination)
            entries[relative] = {"sha256": digest.hexdigest(), "size": size}
    return entries


def _verify_tree(root: Path, entries: dict[str, dict]) -> list[str]:
    """Return a list of mismatches between a tree and its manifest."""
    problems: list[str] = []
    for relative, meta in entries.items():
        path = root / relative
        if "link" in meta:
            if not path.is_symlink() or os.readlink(path) != meta["link"]:
                problems.append(f"{relative}: symlink mismatch")
            continue
        if not path.is_file():
            problems.append(f"{relative}: missing")
            continue
        if path.stat().st_size != meta["size"]:
            problems.append(f"{relative}: size mismatch")
            continue
        if _sha256_file(path) != meta["sha256"]:
            problems.append(f"{relative}: sha256 mismatch")
    if root.is_dir():
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            for name in filenames:
                relative = str((Path(directory) / name).relative_to(root))
                if relative not in entries:
                    problems.append(f"{relative}: not in manifest")
    return problems


def _tree_bytes(entries: dict[str, dict]) -> int:
    return sum(int(m.get("size", 0)) for m in entries.values())


# ---------------------------------------------------------------------------
# create


def create_point(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    data_root = Path(args.data_root).resolve()
    out = Path(args.out)
    if not db_path.is_file():
        raise RestorePointError(f"no database at {db_path}")
    if out.exists():
        raise RestorePointError(f"restore point {out} already exists")
    offenders = read_writer_offenders(db_path)
    if offenders:
        raise WriterActiveError(
            "profiles with an actual writer (stop them first): "
            + ", ".join(offenders)
        )
    profiles = read_profiles(db_path)
    staging = out.parent / (out.name + f".staging-{uuid.uuid4().hex[:12]}")
    staging.mkdir(parents=True)
    try:
        snapshot = staging / "db" / "cbrowser.db"
        snapshot.parent.mkdir(parents=True)
        source = _connect_ro(db_path)
        target = sqlite3.connect(str(snapshot))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        if not _integrity_ok(snapshot):
            raise RestorePointError("database snapshot failed integrity check")
        stamp = _schema_stamp(snapshot)
        if stamp is None:
            raise RestorePointError("database snapshot has no schema stamp")

        manifest_profiles: list[dict] = []
        total_bytes = snapshot.stat().st_size
        for profile in profiles:
            user_dir = Path(profile["user_data_dir"])
            if not user_dir.is_absolute():
                user_dir = data_root / user_dir
            user_dir = user_dir.resolve()
            if not user_dir.is_relative_to(data_root):
                raise RestorePointError(
                    f"profile {profile['id']} user_data_dir {user_dir} is"
                    f" outside the data root {data_root}"
                )
            record: dict = {
                "id": profile["id"],
                "config_version": profile["config_version"],
                "source_user_data_dir": profile["user_data_dir"],
                "dir": None,
                "files": {},
                "bytes": 0,
            }
            if user_dir.is_dir():
                relative = f"profiles/{profile['id']}/profile"
                entries = _copy_tree_manifest(user_dir, staging / relative)
                record["dir"] = relative
                record["files"] = entries
                record["bytes"] = _tree_bytes(entries)
                total_bytes += record["bytes"]
            manifest_profiles.append(record)

        # The point must capture one quiet moment.  A writer that
        # started while the directories were being copied — or a
        # profile row that moved — tears the set (database snapshot
        # and directory bytes from different moments), so re-verify
        # against the live database before anything is published:
        # the same second-check pattern duplicate/reset use (AC-009).
        late_offenders = read_writer_offenders(db_path)
        if late_offenders:
            raise WriterActiveError(
                "profiles acquired a writer during backup: "
                + ", ".join(late_offenders)
            )
        live_versions = {
            p["id"]: p["config_version"] for p in read_profiles(db_path)
        }
        snapshot_versions = {
            p["id"]: p["config_version"] for p in profiles
        }
        if live_versions != snapshot_versions:
            raise WriterActiveError(
                "profile configuration changed during backup; the"
                " point would not capture a single moment"
            )

        prerequisites: list[dict] = []
        if args.secrets_dir:
            secrets_dir = Path(args.secrets_dir)
            if secrets_dir.is_dir():
                for entry in sorted(secrets_dir.iterdir()):
                    if entry.is_file():
                        prerequisites.append(
                            {"name": entry.name, "size": entry.stat().st_size}
                        )
        manifest = {
            "format": FORMAT_VERSION,
            "kind": "cbrowser-restore-point",
            "created_at": _utc_now(),
            "label": args.label,
            "data_root": str(data_root),
            "db": {
                "file": "db/cbrowser.db",
                "sha256": _sha256_file(snapshot),
                "size": snapshot.stat().st_size,
                "integrity": "ok",
                "schema_stamp": stamp,
            },
            "profiles": manifest_profiles,
            "credential_prerequisites": prerequisites,
            "total_bytes": total_bytes,
        }
        _atomic_write_json(staging / "manifest.json", manifest)
        _fsync_dir(staging)
        staging.replace(out)
        _fsync_dir(out.parent)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(str(out))
    return 0


# ---------------------------------------------------------------------------
# verify


def load_manifest(point: Path) -> dict:
    manifest_path = point / "manifest.json"
    if not manifest_path.is_file():
        raise RestorePointError(f"no manifest.json in restore point {point}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise RestorePointError(f"manifest.json is not valid JSON: {exc}") from None
    if manifest.get("format") != FORMAT_VERSION or manifest.get("kind") != (
        "cbrowser-restore-point"
    ):
        raise RestorePointError("manifest is not a cbrowser restore point")
    return manifest


def validate_point(point: Path) -> dict:
    """Full validation of a restore point; raises on the first defect class."""
    manifest = load_manifest(point)
    db_file = point / manifest["db"]["file"]
    if not db_file.is_file():
        raise RestorePointError("restore point database file is missing")
    if db_file.stat().st_size != manifest["db"]["size"]:
        raise RestorePointError("restore point database size mismatch")
    if _sha256_file(db_file) != manifest["db"]["sha256"]:
        raise RestorePointError("restore point database sha256 mismatch")
    if not _integrity_ok(db_file):
        raise RestorePointError("restore point database failed integrity check")
    if _schema_stamp(db_file) != manifest["db"]["schema_stamp"]:
        raise RestorePointError("restore point database schema stamp mismatch")
    for profile in manifest["profiles"]:
        if profile["dir"] is None:
            continue
        problems = _verify_tree(point / profile["dir"], profile["files"])
        if problems:
            raise RestorePointError(
                f"profile {profile['id']} tree mismatch: "
                + "; ".join(problems[:5])
            )
    return manifest


def verify_point(args: argparse.Namespace) -> int:
    manifest = validate_point(Path(args.point))
    print(
        json.dumps(
            {
                "point": args.point,
                "created_at": manifest["created_at"],
                "schema_stamp": manifest["db"]["schema_stamp"],
                "profiles": len(manifest["profiles"]),
                "total_bytes": manifest["total_bytes"],
                "credential_prerequisites": [
                    p["name"] for p in manifest["credential_prerequisites"]
                ],
            },
            indent=2,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# restore


def _default_journal(data_root: Path) -> Path:
    # Inside the data root: that is the one location guaranteed to be
    # on the same persistent volume as the sets being switched (the
    # parent of a container mount point is an ephemeral filesystem,
    # and a lost journal strands a half-switched set with no rollback
    # trigger).  deploy.sh likewise passes an explicit journal path
    # inside the data root (/data/restore-journal.json).
    return data_root / ".restore-journal.json"


def _profile_live_dir(data_root: Path, manifest: dict, profile: dict) -> Path:
    """Map a recorded user_data_dir onto the restore site's data root.

    Recorded paths are absolute in the creating site's view of its data
    root (``/data/profiles/<id>/profile``); the restore site may mount
    its root elsewhere, so the path is re-based by its structure
    relative to the recorded root instead of being used verbatim.
    """
    user_dir = Path(profile["source_user_data_dir"])
    if not user_dir.is_absolute():
        return data_root / user_dir
    recorded_root = manifest.get("data_root")
    if recorded_root:
        try:
            relative = user_dir.relative_to(Path(recorded_root))
        except ValueError:
            raise RestorePointError(
                f"profile {profile['id']} user_data_dir {user_dir} is"
                f" outside the restore point's data root {recorded_root}"
            ) from None
        return data_root / relative
    return user_dir


def _move_sidecars(source: Path, target: Path) -> None:
    """Move a database's -wal/-shm sidecars alongside its main file,
    mirroring the forward switch: a set is only whole with them."""
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(source) + suffix)
        if sidecar.exists():
            sidecar.replace(Path(str(target) + suffix))


def _recover_interrupted(journal_path: Path) -> bool:
    """Roll an interrupted set switch back to the old set.

    Returns True when a recovery ran (the caller must stop and let the
    operator re-run), False when no interrupted switch exists.
    """
    if not journal_path.is_file():
        return False
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal.get("phase") == "complete":
        archive = journal_path.with_name(
            journal_path.name + f".done-{journal['switch_id']}"
        )
        journal_path.replace(archive)
        return False
    for item in reversed(journal["items"]):
        live = Path(item["live_path"])
        previous = Path(item["previous_path"]) if item["previous_path"] else None
        staged = Path(item["staged_path"])
        if item["state"] == "switched":
            if live.exists():
                if staged.is_dir():
                    shutil.rmtree(staged)
                elif staged.exists():
                    staged.unlink()
                live.replace(staged)
                if item.get("sidecars"):
                    _move_sidecars(live, staged)
            if previous is not None and previous.exists():
                previous.replace(live)
                if item.get("sidecars"):
                    _move_sidecars(previous, live)
        elif previous is not None and previous.exists():
            # The switch of this item began (the old set was moved aside)
            # but its journal write never landed.  The staged path is
            # consumed by the second rename, so a missing staged path
            # with a present live path means both renames completed:
            # treat the item as switched and roll it back the same way.
            if live.exists() and not staged.exists():
                live.replace(staged)
                if item.get("sidecars"):
                    _move_sidecars(live, staged)
            if not live.exists():
                previous.replace(live)
                if item.get("sidecars"):
                    _move_sidecars(previous, live)
        if live.parent.is_dir():
            _fsync_dir(live.parent)
    journal["phase"] = "rolled_back"
    journal["updated_at"] = _utc_now()
    archive = journal_path.with_name(
        journal_path.name + f".rolled-back-{journal['switch_id']}"
    )
    _atomic_write_json(journal_path, journal)
    journal_path.replace(archive)
    return True


def restore_point(args: argparse.Namespace) -> int:
    point = Path(args.point)
    db_path = Path(args.db)
    data_root = Path(args.data_root).resolve()
    journal_path = (
        Path(args.journal) if args.journal else _default_journal(data_root)
    )
    if _recover_interrupted(journal_path):
        print(
            "restore_point: an interrupted switch was rolled back to the"
            " previous set; re-run restore to proceed",
            file=sys.stderr,
        )
        return 3

    manifest = validate_point(point)
    if db_path.is_file():
        live_stamp = _schema_stamp(db_path)
        if live_stamp != manifest["db"]["schema_stamp"]:
            raise RestorePointError(
                f"schema stamp mismatch: restore point has"
                f" {manifest['db']['schema_stamp']}, live database has"
                f" {live_stamp}; cross-generation restore is refused"
            )

    # Staging leftovers of a run killed before its journal was
    # written can never be resumed (their switch id is gone with the
    # process); sweep them so repeated incidents do not accumulate
    # profile-sized orphans next to the live set.  The retained
    # .pre-restore-* sets are never swept — they are the rollback
    # guarantee, not debris.
    for stale in db_path.parent.glob(db_path.name + ".restore-staging-*"):
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
        else:
            stale.unlink(missing_ok=True)
    for profile in manifest["profiles"]:
        profile_parent = _profile_live_dir(
            data_root, manifest, profile
        ).parent
        for stale in profile_parent.glob(".restore-staging-*"):
            if stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)

    switch_id = uuid.uuid4().hex[:12]
    # Stage validated copies next to their targets (same filesystems).
    # An empty restore site (fresh install) has neither directory yet.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    db_staged = db_path.with_name(db_path.name + f".restore-staging-{switch_id}")
    db_previous = db_path.with_name(db_path.name + f".pre-restore-{switch_id}")
    disk = shutil.disk_usage(db_path.parent)
    if disk.free < manifest["db"]["size"]:
        raise RestorePointError("insufficient free space on the database volume")
    shutil.copyfile(point / manifest["db"]["file"], db_staged)
    if _sha256_file(db_staged) != manifest["db"]["sha256"]:
        db_staged.unlink(missing_ok=True)
        raise RestorePointError("staged database copy failed verification")
    items.append(
        {
            "kind": "db",
            "id": "control-db",
            "live_path": str(db_path),
            "staged_path": str(db_staged),
            "previous_path": str(db_previous) if db_path.exists() else None,
            "state": "pending",
            "sidecars": True,
        }
    )
    profiles_bytes = sum(p["bytes"] for p in manifest["profiles"])
    disk = shutil.disk_usage(data_root)
    if disk.free < profiles_bytes:
        raise RestorePointError("insufficient free space on the data root")
    for profile in manifest["profiles"]:
        live_dir = _profile_live_dir(data_root, manifest, profile)
        staged_dir = live_dir.with_name(f".restore-staging-{switch_id}")
        previous_dir = live_dir.with_name(f".pre-restore-{switch_id}")
        if staged_dir.exists():
            shutil.rmtree(staged_dir)
        if profile["dir"] is not None:
            entries = _copy_tree_manifest(point / profile["dir"], staged_dir)
            if entries != profile["files"]:
                shutil.rmtree(staged_dir, ignore_errors=True)
                raise RestorePointError(
                    f"staged copy of profile {profile['id']} failed verification"
                )
        items.append(
            {
                "kind": "profile",
                "id": profile["id"],
                "live_path": str(live_dir),
                "staged_path": str(staged_dir),
                "previous_path": str(previous_dir) if live_dir.exists() else None,
                "state": "pending",
                "sidecars": False,
            }
        )

    journal = {
        "version": FORMAT_VERSION,
        "switch_id": switch_id,
        "phase": "switching",
        "point": str(point),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "items": items,
    }
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(journal_path, journal)
    try:
        for item in items:
            live = Path(item["live_path"])
            staged = Path(item["staged_path"])
            previous = Path(item["previous_path"]) if item["previous_path"] else None
            moved = False
            if previous is not None and live.exists():
                live.replace(previous)
                if item.get("sidecars"):
                    for suffix in ("-wal", "-shm"):
                        sidecar = Path(str(live) + suffix)
                        if sidecar.exists():
                            sidecar.replace(Path(str(previous) + suffix))
                moved = True
            if item["kind"] == "db" or (point_has_dir(manifest, item["id"])):
                staged.replace(live)
                moved = True
            if moved:
                # The renames must be durable before the journal
                # records them, or a power loss could leave the
                # journal ahead of the filesystem it describes.
                _fsync_dir(live.parent)
            item["state"] = "switched"
            journal["updated_at"] = _utc_now()
            _atomic_write_json(journal_path, journal)
    except BaseException:
        print(
            "restore_point: switch interrupted; run restore again to roll"
            " back to the previous set",
            file=sys.stderr,
        )
        raise
    journal["phase"] = "complete"
    journal["updated_at"] = _utc_now()
    _atomic_write_json(journal_path, journal)
    print(
        f"restored {point} (switch {switch_id}); previous set retained at"
        f" *.pre-restore-{switch_id} next to the restored targets"
    )
    return 0


def point_has_dir(manifest: dict, profile_id: str) -> bool:
    for profile in manifest["profiles"]:
        if profile["id"] == profile_id:
            return profile["dir"] is not None
    return False


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a restore point")
    create.add_argument("--db", required=True)
    create.add_argument("--data-root", required=True)
    create.add_argument("--out", required=True)
    create.add_argument("--secrets-dir")
    create.add_argument("--label")
    create.set_defaults(func=create_point)

    verify = sub.add_parser("verify", help="validate a restore point")
    verify.add_argument("--point", required=True)
    verify.set_defaults(func=verify_point)

    restore = sub.add_parser("restore", help="restore a restore point")
    restore.add_argument("--point", required=True)
    restore.add_argument("--db", required=True)
    restore.add_argument("--data-root", required=True)
    restore.add_argument("--journal")
    restore.set_defaults(func=restore_point)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except WriterActiveError as exc:
        print(f"restore_point: {exc}", file=sys.stderr)
        return 2
    except RestorePointError as exc:
        print(f"restore_point: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
