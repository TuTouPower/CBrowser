"""Read immutable image references from a cbrowser distribution manifest."""

import argparse
import json
import re
import sys
from pathlib import Path

ROLES = ("api", "browser", "caddy", "gateway", "stream", "supervisor")
IMAGE_ID = r"sha256:[0-9a-f]{64}"
REPOSITORY = r"[a-z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+"


def read_images(path: Path, mode: str) -> dict[str, str]:
    images = json.loads(path.read_text())["images"]
    if not isinstance(images, dict) or set(images) != set(ROLES):
        raise ValueError("image manifest must specify exactly the six service roles")
    pattern = IMAGE_ID if mode == "local" else rf"{REPOSITORY}@{IMAGE_ID}"
    for role, ref in images.items():
        if not isinstance(ref, str) or not re.fullmatch(pattern, ref):
            raise ValueError(f"{role}: expected an immutable {mode} image reference")
    return images


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("local", "registry"))
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        images = read_images(args.manifest, args.mode)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write(f"Invalid image manifest: {exc}\n")
        return 1
    sys.stdout.writelines(f"{role} {images[role]}\n" for role in ROLES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
