import hashlib
import io
import tarfile

import pytest

from cbrowser.font_sets.manifest import import_font_set
from scripts.font_bundle import seed


def test_bundle_seeds_both_platforms_and_can_be_retried(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "font.ttf").write_bytes(b"font fixture")
    sets = tmp_path / "sets"
    locked = {
        platform: import_font_set(platform, [source], "fixture", root=sets)["set_id"]
        for platform in ("windows", "macos")
    }
    archive = tmp_path / "fonts.tar.zst"
    with tarfile.open(archive, "w:zst") as bundle:
        for platform in locked:
            bundle.add(sets / platform, arcname=platform)
    lock = {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "sets": locked}
    destination = tmp_path / "destination"
    seed(archive, lock, destination)
    manifests = [destination / platform / set_id / "manifest.json" for platform, set_id in locked.items()]
    before = [path.stat().st_mtime_ns for path in manifests]
    seed(archive, lock, destination)
    assert [path.stat().st_mtime_ns for path in manifests] == before


def test_bundle_refuses_an_archive_with_a_matching_hash_but_unsafe_path(tmp_path):
    archive = tmp_path / "fonts.tar.zst"
    payload = b"unsafe"
    with tarfile.open(archive, "w:zst") as bundle:
        member = tarfile.TarInfo("../outside.ttf")
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))
    lock = {
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "sets": {"windows": "a" * 64, "macos": "b" * 64},
    }
    with pytest.raises(ValueError, match="Unexpected archive member"):
        seed(archive, lock, tmp_path / "destination")
    assert not (tmp_path / "outside.ttf").exists()


def test_bundle_rejects_lock_missing_a_platform(tmp_path):
    archive = tmp_path / "fonts.tar.zst"
    with tarfile.open(archive, "w:zst"):
        pass
    lock = {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "sets": {"windows": "a" * 64}}
    destination = tmp_path / "destination"
    with pytest.raises(ValueError, match="Windows and macOS set IDs"):
        seed(archive, lock, destination)
    assert not destination.exists()
