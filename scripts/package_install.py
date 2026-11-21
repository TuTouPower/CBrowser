"""Create an installer from the checked-out commit and a pinned registry manifest."""

import argparse
import io
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

from image_manifest import read_images

ROOT = Path(__file__).resolve().parents[1]
INSTALL_PATHS = (
    "install.sh",
    "compose.yaml",
    "DOCKER_DEPLOYMENT.md",
    "config/font_assets.lock.json",
    "scripts",
    "src/backend",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    images = read_images(args.manifest, "registry")
    files = subprocess.check_output(["git", "archive", "HEAD", "--", *INSTALL_PATHS], cwd=ROOT)
    manifest = (json.dumps({"images": images}, indent=2) + "\n").encode()
    member = tarfile.TarInfo("images.json")
    member.size = len(manifest)
    with tempfile.NamedTemporaryFile(dir=args.output.parent) as staged:
        with (
            tarfile.open(fileobj=io.BytesIO(files), mode="r:") as source,
            tarfile.open(fileobj=staged, mode="w:gz") as package,
        ):
            for entry in source:
                payload = source.extractfile(entry) if entry.isfile() else None
                package.addfile(entry, payload)
            package.addfile(member, io.BytesIO(manifest))
        staged.flush()
        os.fsync(staged.fileno())
        os.link(staged.name, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
