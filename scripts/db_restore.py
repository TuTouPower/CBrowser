#!/usr/bin/env python3
"""Restore the control-plane database from a backup file (t051).

Runs inside the API image while the stack is down:

    docker run --rm -v <db-volume>:/db -v <backup-dir>:/backup:ro \\
        <api-image> python3 /scripts/db_restore.py \\
        --backup /backup/cbrowser-<ts>.db --db /db/cbrowser.db

The backup is copied over the live database file; stale `-wal`/`-shm`
sidecars are removed first so no pre-restore write-ahead state survives.
The stack must be down (deploy.sh runs `compose down` first) and the
user re-deploys afterwards.  Never deletes the backup itself.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, help="Backup file to restore")
    parser.add_argument("--db", required=True, help="Live database file")
    args = parser.parse_args(argv)
    backup_path, db_path = Path(args.backup), Path(args.db)
    if not backup_path.is_file():
        print(f"db_restore: no backup at {args.backup}", file=sys.stderr)
        return 1
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(backup_path, db_path)
    print(f"restored {args.db} from {args.backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
