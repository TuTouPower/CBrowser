"""Controller file writes replace a hostile symlink instead of following it."""

from cbrowser.supervisor.file_storage import atomic_write_text


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
