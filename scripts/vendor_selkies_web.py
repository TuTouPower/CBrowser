"""Vendors official Selkies 2.1.0 web assets and injects the adapter tag."""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
import shutil
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger("cbrowser.vendor_selkies_web")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = REPO_ROOT / "config" / "selkies" / "selkies_web_sha256.txt"

PINNED_SELKIES_VERSION = "2.1.0"
PINNED_WHEEL_SHA256 = "8bde6207ca921cb2f38c3204fafe18d40b5578165894818ae1ca9e46fca7b966"
PINNED_WHEEL_FILENAME = f"selkies-{PINNED_SELKIES_VERSION}-py3-none-any.whl"
PINNED_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/48/39/"
    "64b75999a7a45a1bf063cc31f2a3fda9da65dafb0fb7a6567ecde9674891/"
    f"selkies-{PINNED_SELKIES_VERSION}-py3-none-any.whl"
)


def _safe_relative_path(name: str) -> str:
    if name.startswith(("/", "\\")):
        raise RuntimeError("Unsafe archive member path")
    rel = name.replace("\\", "/")
    if not rel or rel.startswith("../") or "/../" in f"/{rel}/" or rel in {".", ".."}:
        raise RuntimeError("Unsafe archive member path")
    return rel


def verify_manifest(
    extracted_dir: Path,
    manifest_path: Path,
    allow_patched: bool = False,
) -> None:
    """Verifies that extracted official files match reference sha256 manifest."""
    if not manifest_path.is_file():
        raise RuntimeError(f"Reference manifest not found at {manifest_path}")
    manifest_lines = manifest_path.read_text(encoding="utf-8").splitlines()
    expected_files: set[str] = set()
    for line in manifest_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        expected_hash, rel_path = line.split(None, 1)
        clean_rel = _safe_relative_path(rel_path.removeprefix("selkies_web/").strip())
        expected_files.add(clean_rel)
        file_path = extracted_dir / clean_rel

        # If patched index.html is allowed, check the backup if present
        if allow_patched and clean_rel == "index.html":
            official_backup = extracted_dir / "index.html.official"
            if official_backup.is_file():
                file_path = official_backup

        if not file_path.is_file():
            raise RuntimeError(f"Official Selkies asset missing: {clean_rel}")
        content = file_path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"SHA256 mismatch for {clean_rel}: {expected_hash} != {actual_hash}"
            )
    ignored = {"index.html.official", ".DS_Store", "build-stamp.json"}
    if allow_patched:
        ignored.add("selkies_adapter.js")
    actual_files = {
        path.relative_to(extracted_dir).as_posix()
        for path in extracted_dir.rglob("*")
        if path.is_file()
        and path.name not in ignored
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }
    unexpected = actual_files - expected_files
    if unexpected:
        raise RuntimeError(
            "Extracted Selkies assets contain files outside the manifest: "
            + ", ".join(sorted(unexpected))
        )


def download_wheel(cache_dir: Path) -> Path:
    """Downloads pinned wheel into cache_dir and verifies SHA-256."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = cache_dir / PINNED_WHEEL_FILENAME

    if wheel_path.is_file():
        actual_hash = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
        if actual_hash == PINNED_WHEEL_SHA256:
            return wheel_path

    logger.info("Downloading wheel %s ...", PINNED_WHEEL_URL)
    with urllib.request.urlopen(PINNED_WHEEL_URL, timeout=60.0) as resp:
        data = resp.read()

    actual_hash = hashlib.sha256(data).hexdigest()
    if actual_hash != PINNED_WHEEL_SHA256:
        raise RuntimeError(
            f"Wheel hash mismatch: {PINNED_WHEEL_SHA256} != {actual_hash}"
        )

    wheel_path.write_bytes(data)
    return wheel_path


def extract_from_wheel(wheel_path: Path, dest_dir: Path) -> None:
    """Extracts selkies_web from wheel zip archive into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel_path) as z:
        prefix = "selkies/selkies_web/"
        for info in z.infolist():
            if not info.filename.startswith(prefix) or info.is_dir():
                continue
            rel = _safe_relative_path(info.filename.removeprefix(prefix))
            if "__pycache__" in rel or rel.endswith(".pyc"):
                continue
            out_file = dest_dir / rel
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(z.read(info.filename))


def extract_from_stream_image(image_id: str, dest_dir: Path) -> None:
    """Extracts selkies_web from Stream Docker image container."""
    import tarfile

    import docker

    client = docker.from_env()
    container = client.containers.create(
        image_id, entrypoint=["/bin/sh"], command=["-c", "sleep 60"]
    )
    try:
        container.start()
        # Locate selkies_web inside the image instead of freezing a Python
        # minor version in the path (t034 upgrades the runtime to 3.15).
        result = container.exec_run(
            ["find", "/opt/venv", "/usr/local/lib", "-maxdepth", "6",
             "-type", "d", "-name", "selkies_web", "-print", "-quit"],
        )
        found = (result.output or b"").decode("utf-8", "replace").strip()
        if result.exit_code != 0 or not found:
            raise FileNotFoundError(
                "selkies_web not found in Stream image (dynamic discovery failed)"
            )
        archive_stream, _ = container.get_archive(found.splitlines()[0])
        archive_bytes = b"".join(archive_stream)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as tar:
            for member in tar.getmembers():
                if member.isdir():
                    continue
                name = _safe_relative_path(member.name.removeprefix("selkies_web/").removeprefix(
                    "selkies_web"
                ))
                if not name or "__pycache__" in name or name.endswith(".pyc"):
                    continue
                f = tar.extractfile(member)
                if f is not None:
                    out_path = dest_dir / name
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(f.read())
    finally:
        container.remove(force=True)


def vendor_selkies_web(
    dest_dir: Path,
    wheel_path: Path | None = None,
    image_id: str | None = None,
    cache_dir: Path | None = None,
    manifest_path: Path | None = None,
    inject_adapter: bool = True,
) -> Path:
    """Extracts, verifies, and optionally injects Selkies web client."""
    repo_root = Path(__file__).resolve().parent.parent
    if manifest_path is None:
        manifest_path = DEFAULT_MANIFEST_PATH
    if cache_dir is None:
        cache_dir = repo_root / ".scratch" / "selkies_wheels"

    # Generated directory: replace it so stale files never reach the build.
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)

    # Strategy 1: Explicit wheel path
    if wheel_path and wheel_path.is_file():
        h = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
        if h != PINNED_WHEEL_SHA256:
            raise RuntimeError(f"Wheel hash mismatch: {PINNED_WHEEL_SHA256} != {h}")
        extract_from_wheel(wheel_path, dest_dir)
    # Strategy 2: Explicit docker image
    elif image_id:
        extract_from_stream_image(image_id, dest_dir)
    # Strategy 3: Check cached wheel in cache_dir
    elif (cache_dir / PINNED_WHEEL_FILENAME).is_file():
        cached_whl = cache_dir / PINNED_WHEEL_FILENAME
        h = hashlib.sha256(cached_whl.read_bytes()).hexdigest()
        if h == PINNED_WHEEL_SHA256:
            extract_from_wheel(cached_whl, dest_dir)
        else:
            whl = download_wheel(cache_dir)
            extract_from_wheel(whl, dest_dir)
    # Strategy 4: Download wheel
    else:
        whl = download_wheel(cache_dir)
        extract_from_wheel(whl, dest_dir)

    # Verify pristine official manifest
    verify_manifest(dest_dir, manifest_path=manifest_path, allow_patched=False)

    # Backup official index.html
    index_file = dest_dir / "index.html"
    official_backup = dest_dir / "index.html.official"
    if index_file.is_file() and not official_backup.is_file():
        shutil.copy2(index_file, official_backup)

    # Inject the classic adapter script produced by the frontend build
    if inject_adapter:
        raw_html = official_backup.read_text(encoding="utf-8")
        adapter_tag = '<script src="./selkies_adapter.js"></script>'
        marker = (
            '<script type="module" crossorigin '
            'src="./assets/index-BpOBp7NB.js"></script>'
        )
        if marker in raw_html:
            adapted_html = raw_html.replace(marker, adapter_tag + "\n" + marker, 1)
        elif "<head>" in raw_html:
            adapted_html = raw_html.replace("<head>", "<head>\n" + adapter_tag, 1)
        else:
            adapted_html = adapter_tag + "\n" + raw_html
        index_file.write_text(adapted_html, encoding="utf-8")

    return dest_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Vendor Selkies 2.1.0 web client assets with verified SHA256 integrity"
        )
    )
    repo_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=repo_root / "src" / "frontend" / "public" / "selkies",
        help="Destination directory for vendored web client assets",
    )
    parser.add_argument(
        "--wheel", type=Path, default=None, help="Path to local wheel file"
    )
    parser.add_argument(
        "--image", type=str, default=None, help="Docker Stream image ID to extract from"
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=repo_root / ".scratch" / "selkies_wheels",
        help="Directory to cache downloaded wheel",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to reference sha256 manifest file",
    )
    parser.add_argument(
        "--no-inject-adapter",
        action="store_true",
        help="Skip injecting SelkiesClientAdapter into index.html",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    vendor_selkies_web(
        dest_dir=args.dest_dir,
        wheel_path=args.wheel,
        image_id=args.image,
        cache_dir=args.cache_dir,
        manifest_path=args.manifest,
        inject_adapter=not args.no_inject_adapter,
    )
    print(f"Successfully vendored Selkies web client to {args.dest_dir}")


if __name__ == "__main__":
    main()
