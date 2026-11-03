"""Security boundaries for vendored Selkies archives."""

from hashlib import sha256
from pathlib import Path

import pytest

from scripts.vendor_selkies_web import _safe_relative_path, verify_manifest


@pytest.mark.parametrize("name", ["../escape", "a/../../b", "..", "", "/absolute", "..\\\\escape"])
def test_archive_member_traversal_is_rejected(name: str) -> None:
    with pytest.raises(RuntimeError, match="Unsafe archive member path"):
        _safe_relative_path(name)


def test_manifest_rejects_unlisted_file(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    official = extracted / "index.html"
    official.write_text("official", encoding="utf-8")
    manifest = tmp_path / "manifest.txt"
    digest = sha256(official.read_bytes()).hexdigest()
    manifest.write_text(f"{digest}  selkies_web/index.html\n", encoding="utf-8")
    (extracted / "extra.js").write_text("unexpected", encoding="utf-8")

    with pytest.raises(RuntimeError, match="outside the manifest"):
        verify_manifest(extracted, manifest)


def test_zip_extraction_rejects_traversal_member(tmp_path: Path) -> None:
    import zipfile

    from scripts.vendor_selkies_web import extract_from_wheel

    wheel = tmp_path / "evil.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("selkies/selkies_web/../escape.js", "evil")
    with pytest.raises(RuntimeError, match="Unsafe archive member path"):
        extract_from_wheel(wheel, tmp_path / "out")
