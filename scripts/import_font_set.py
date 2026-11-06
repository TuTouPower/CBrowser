"""Import platform fonts into a content-addressed, immutable font set."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "backend"))

from cbrowser.font_sets import import_font_set

LOGGER = logging.getLogger("import_font_set")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import platform font files as an immutable, content-addressed font set."
        )
    )
    parser.add_argument("--platform", required=True, choices=["windows", "macos"])
    parser.add_argument("--source", required=True, action="append", metavar="DIR")
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--fonts-dir", default=None, metavar="ROOT")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    LOGGER.info(
        "Importing %s fonts from %d source directory(ies)",
        args.platform,
        len(args.source),
    )
    try:
        result = import_font_set(
            args.platform,
            args.source,
            args.source_version,
            root=args.fonts_dir,
        )
    except (ValueError, OSError) as exc:
        LOGGER.error("Import failed: %s", exc)
        return 1
    LOGGER.info("Font set %s created=%s", result["set_id"], result["created"])
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
