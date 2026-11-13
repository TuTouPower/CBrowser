"""The shared atomic-write primitive (t062): hostile-symlink safety,
failure atomicity and staging-file ownership."""

from types import SimpleNamespace

import pytest

from cbrowser.shared import atomic_write
from cbrowser.shared.atomic_write import atomic_write_text


def test_snapshot_write_does_not_overwrite_symlink_target(tmp_path):
    victim = tmp_path / "other_profile.json"
    victim.write_text("untouched")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    snapshot = runtime / "snapshot.json"
    snapshot.symlink_to(victim)
    atomic_write_text(snapshot, "new snapshot", mode=0o644)
    assert victim.read_text() == "untouched"
    assert not snapshot.is_symlink()
    assert snapshot.read_text() == "new snapshot"
    assert not list(runtime.glob("*.tmp"))


def test_failed_write_preserves_previous_file_and_cleans_staging(
    tmp_path, monkeypatch
):
    target = tmp_path / "state.json"
    target.write_text("previous")

    def _fail_replace(self, _other):
        raise OSError("replace failed")

    monkeypatch.setattr(type(target), "replace", _fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(target, "new")
    assert target.read_text() == "previous"
    assert not list(tmp_path.glob("*.tmp"))


def test_staging_collision_never_deletes_another_writer(tmp_path, monkeypatch):
    occupied = tmp_path / "collision.tmp"
    occupied.write_bytes(b"another writer")
    monkeypatch.setattr(
        atomic_write.uuid, "uuid4", lambda: SimpleNamespace(hex="collision")
    )
    with pytest.raises(FileExistsError):
        atomic_write_text(tmp_path / "state.json", "new")
    assert occupied.read_bytes() == b"another writer"
