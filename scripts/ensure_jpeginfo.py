"""Deterministically provide the strict JPEG validator for the gate.

``PreviewCaptureLoop`` validates committed frames with ``jpeginfo --check -``
(d040): the strict libjpeg codestream check that Pillow's tolerant decoder
cannot provide (it fills a truncated frame repaired with a trailing EOI with
grey pixels instead of failing).  That binary ships inside the Browser image
but is not a Python dependency, so the gate's single entry point owns it.

Contract: reuse a binary on PATH or in the gitignored scratch cache, verify it
against the exact d040 contract (legal frame -> 0, truncated frame with a
repaired EOI -> nonzero), then expose its directory on PATH.  Nothing is
installed system-wide and no public download is attempted; a missing or
nonconforming binary fails closed with an actionable message before any suite
runs -- the same rule as ``ensure_selkies_wheel_cache``.

The gate prints only the containing directory on stdout so the caller can
prepend it to PATH; all diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = REPO_ROOT / ".scratch" / "jpeginfo"
BINARY_NAME = "jpeginfo"


def _samples() -> tuple[bytes, bytes]:
    from PIL import Image

    with io.BytesIO() as output:
        Image.new("RGB", (480, 300), "white").save(output, "JPEG", quality=70)
        legal = output.getvalue()
    # d040: truncating entropy-coded data and appending a fresh EOI is
    # tolerated by Pillow but must be rejected by the strict decoder.
    truncated = legal[:-1000] + b"\xff\xd9"
    return legal, truncated


def _check(binary: str) -> tuple[bool, str]:
    legal, truncated = _samples()
    try:
        legal_rc = subprocess.run(
            [binary, "--check", "-"],
            input=legal,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        ).returncode
        truncated_rc = subprocess.run(
            [binary, "--check", "-"],
            input=truncated,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        ).returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if legal_rc != 0 or truncated_rc == 0:
        return False, (
            f"d040 contract violated (legal={legal_rc}, truncated={truncated_rc})"
        )
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    args = parser.parse_args()
    cache = Path(args.cache_dir)

    candidates: list[Path] = []
    system = shutil.which(BINARY_NAME)
    if system:
        candidates.append(Path(system))
    candidates.append(cache / BINARY_NAME)

    for binary in candidates:
        if not binary.is_file():
            continue
        valid, reason = _check(str(binary))
        if valid:
            print(f"jpeginfo ready: {binary}", file=sys.stderr)
            print(str(binary.parent))
            return 0
        print(f"jpeginfo rejected {binary}: {reason}", file=sys.stderr)

    print(
        "Strict JPEG validator unavailable. Build upstream jpeginfo v1.7.1 "
        f"into {cache / BINARY_NAME} (out of band, no system install) and "
        "re-run. The binary must satisfy the d040 contract: "
        "`jpeginfo --check -` accepts a legal frame and rejects a truncated "
        "frame with a repaired EOI.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
