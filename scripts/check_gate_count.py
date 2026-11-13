"""Fail closed when a gate silently collects fewer cases than its baseline."""

from __future__ import annotations

import argparse
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

# Reviewed baselines; maintained with docs/blueprint/testing.md.
MINIMUM_CASES = {
    "contract": 258,
    "unit": 1654,
    "integration": 196,
    "e2e": 105,
    "frontend_test": 499,
}
logger = logging.getLogger(__name__)


def check_count(suite: str, count: int) -> bool:
    minimum = MINIMUM_CASES.get(suite, 1)
    if count < minimum:
        logger.error("gate %s: %d cases below minimum %d", suite, count, minimum)
        return False
    logger.info("gate %s: %d cases (minimum %d)", suite, count, minimum)
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--junit", type=Path)
    source.add_argument("--vitest", type=Path)
    args = parser.parse_args()
    try:
        if args.junit:
            count = len(list(ET.parse(args.junit).getroot().iter("testcase")))
        else:
            count = json.loads(args.vitest.read_text())["numTotalTests"]
        return 0 if check_count(args.suite, count) else 1
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        logger.error("gate %s: invalid case report: %s", args.suite, exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
