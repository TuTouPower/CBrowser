#!/usr/bin/env python3
"""Back up the control-plane database with the SQLite online-backup API (t051).

Runs inside the API image before `compose up` so the live database is
copied consistently while the stack is still down:

    docker run --rm -v <db-volume>:/db -v <backup-dir>:/backup \\
        <api-image> python3 /scripts/db_backup.py \\
        --db /db/cbrowser.db --out /backup/cbrowser-<ts>.db

The source is opened read-only; the backup file is a complete, valid
SQLite database that `db_restore.py` can copy back.  Exits non-zero when
the source cannot be read.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Source SQLite database")
    parser.add_argument("--out", required=True, help="Backup file to write")
    args = parser.parse_args(argv)
    source_path, out_path = Path(args.db), Path(args.out)
    if not source_path.is_file():
        print(f"db_backup: no database at {args.db}", file=sys.stderr)
        return 1
    source = None
    target = None
    try:
        source = sqlite3.connect(
            "file:" + quote(str(source_path)) + "?mode=ro", uri=True
        )
        target = sqlite3.connect(str(out_path))
        source.backup(target)
    except sqlite3.DatabaseError as exc:
        print(f"db_backup: failed to back up {args.db}: {exc}", file=sys.stderr)
        return 1
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
