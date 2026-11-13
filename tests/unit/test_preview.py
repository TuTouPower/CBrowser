from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from cbrowser.preview import (
    PreviewMeta,
    PreviewPolicy,
    clear_preview,
    commit_preview,
    preview_dir,
    read_meta,
    read_policy,
    write_policy,
)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_preview_dir_is_isolated_from_user_data(tmp_path: Path) -> None:
    assert preview_dir(tmp_path, "p1") == tmp_path / "profiles" / "p1" / "preview"
    assert (
        preview_dir(tmp_path, "p1")
        != tmp_path / "profiles" / "p1" / "profile" / "preview"
    )


def test_policy_roundtrip_is_atomic_and_private(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=3, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    assert read_policy(directory) == policy
    assert mode(directory / "policy.json") == 0o600


def test_policy_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_policy(preview_dir(tmp_path, "p1")) is None


def test_atomic_write_removes_tmp_on_failure(tmp_path: Path, monkeypatch) -> None:
    import os as _os

    def _fail_chmod(*_args, **_kwargs) -> None:
        raise OSError("chmod failed")

    # The write mechanism is the shared atomic-write primitive (t062),
    # which sets the mode with fchmod on the staging descriptor.
    monkeypatch.setattr(_os, "fchmod", _fail_chmod)
    directory = preview_dir(tmp_path, "p9")
    with pytest.raises(OSError, match="chmod failed"):
        write_policy(
            directory,
            PreviewPolicy(enabled=True, epoch=1, runtime_instance_id=None),
        )
    assert list(directory.glob("*.tmp")) == []
    assert not (directory / "policy.json").exists()


def test_meta_json_never_contains_image_bytes(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at="2026-11-07T12:00:00+00:00",
        runtime_instance_id="inst-1",
        policy_epoch=2,
    )
    assert commit_preview(directory, b"\xff\xd8jpeg", meta, policy)
    raw = (directory / "meta.json").read_text(encoding="utf-8")
    assert "jpeg" not in raw
    assert json.loads(raw)["policy_epoch"] == 2


def test_concurrent_policy_writers_own_their_staging_files(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from cbrowser import preview

    barrier = Barrier(3)
    original = preview.os.replace
    sources = []

    def rendezvous(source, target):
        sources.append(source)
        barrier.wait(timeout=5)
        return original(source, target)

    monkeypatch.setattr(preview.os, "replace", rendezvous)
    directory = preview_dir(tmp_path, "p")
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [
            pool.submit(write_policy, directory, PreviewPolicy(enabled=True, epoch=i))
            for i in range(3)
        ]
        for job in jobs:
            job.result()
    assert len(set(sources)) == 3
    assert list(directory.glob(".*.tmp")) == []
    assert read_policy(directory).epoch in range(3)


def test_reader_keeps_open_frame_across_replacement_and_clear(tmp_path, monkeypatch):
    from cbrowser import preview

    directory = preview_dir(tmp_path, "p")
    policy = PreviewPolicy(enabled=True, epoch=1, runtime_instance_id="i")
    write_policy(directory, policy)
    old = PreviewMeta(
        captured_at="2026-11-12T01:00:00Z", runtime_instance_id="i", policy_epoch=1
    )
    new = PreviewMeta(
        captured_at="2026-11-12T01:00:01Z", runtime_instance_id="i", policy_epoch=1
    )
    assert commit_preview(directory, b"first", old, policy)
    original = Path.open
    raced = False

    def open_then_replace(path, *args, **kwargs):
        nonlocal raced
        handle = original(path, *args, **kwargs)
        if path.suffix == ".jpg" and not raced:
            raced = True
            clear_preview(directory)
            assert commit_preview(directory, b"second", new, policy)
        return handle

    monkeypatch.setattr(Path, "open", open_then_replace)
    metadata, data = preview.read_preview(
        directory, policy, epoch=1, runtime_instance_id="i"
    )
    assert raced
    assert metadata.captured_at == old.captured_at
    assert data == b"first"
    metadata, data = preview.read_preview(
        directory, policy, epoch=1, runtime_instance_id="i"
    )
    assert metadata.captured_at == new.captured_at
    assert data == b"second"


def test_committed_frame_is_private_and_selected_by_atomic_metadata(tmp_path):
    from cbrowser.preview import frame_path, read_preview

    directory = preview_dir(tmp_path, "p")
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="i")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at="2026-11-12T00:00:00Z", runtime_instance_id="i", policy_epoch=2
    )
    assert commit_preview(directory, b"first", meta, policy)
    selected = read_meta(directory)
    frame = frame_path(directory, selected)
    assert frame.read_bytes() == b"first"
    assert mode(frame) == mode(directory / "meta.json") == 0o600
    assert read_preview(directory, policy, epoch=2, runtime_instance_id="i") == (
        selected,
        b"first",
    )
    replacement = meta.model_copy(update={"captured_at": "2026-11-12T00:00:01Z"})
    assert commit_preview(directory, b"next", replacement, policy)
    assert frame.read_bytes() == b"first"
    assert frame_path(directory, read_meta(directory)) != frame
    assert not (directory / "latest.jpg").exists()


def test_exclusive_staging_collision_never_deletes_another_writer(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from cbrowser import preview

    tmp_path.mkdir(exist_ok=True)
    occupied = tmp_path / "collision.tmp"
    occupied.write_bytes(b"another writer")
    from cbrowser.shared import atomic_write

    monkeypatch.setattr(
        atomic_write.uuid, "uuid4", lambda: SimpleNamespace(hex="collision")
    )
    with pytest.raises(FileExistsError):
        write_policy(tmp_path, PreviewPolicy(enabled=True, epoch=1))
    assert occupied.read_bytes() == b"another writer"


def test_metadata_failure_preserves_previous_frame(tmp_path, monkeypatch):
    from cbrowser import preview

    policy = PreviewPolicy(enabled=True, epoch=1, runtime_instance_id="i")
    write_policy(tmp_path, policy)
    first = PreviewMeta(captured_at="t1", runtime_instance_id="i", policy_epoch=1)
    assert commit_preview(tmp_path, b"first", first, policy)
    original = preview._atomic_write

    def fail_meta(path, payload, **kwargs):
        if path.name == "meta.json":
            raise OSError("metadata interrupted")
        original(path, payload, **kwargs)

    monkeypatch.setattr(preview, "_atomic_write", fail_meta)
    with pytest.raises(OSError):
        commit_preview(
            tmp_path, b"second", first.model_copy(update={"captured_at": "t2"}), policy
        )
    assert preview.read_preview(tmp_path, policy, epoch=1, runtime_instance_id="i") == (
        first,
        b"first",
    )


@pytest.mark.parametrize(
    "enabled,epoch,instance",
    [(False, 2, "i"), (False, 3, "i"), (True, 3, "i"), (True, 2, "new")],
)
def test_stale_frame_cannot_publish_or_clear_new_authorized_frame(
    tmp_path, enabled, epoch, instance
):
    from cbrowser.preview import read_preview

    expected = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="i")
    live = PreviewPolicy(enabled=enabled, epoch=epoch, runtime_instance_id=instance)
    write_policy(tmp_path, live)
    before = None
    if enabled:
        fresh = PreviewMeta(
            captured_at="fresh", runtime_instance_id=instance, policy_epoch=epoch
        )
        assert commit_preview(tmp_path, b"fresh", fresh, live)
        before = read_preview(tmp_path, live, epoch=epoch, runtime_instance_id=instance)
    stale = PreviewMeta(captured_at="late", runtime_instance_id="i", policy_epoch=2)
    assert not commit_preview(tmp_path, b"late", stale, expected)
    assert (
        read_preview(tmp_path, live, epoch=epoch, runtime_instance_id=instance)
        == before
    )
    if not enabled:
        assert list(tmp_path.glob("*.jpg")) == []
        assert read_meta(tmp_path) is None


def test_clear_removes_current_and_retained_frames_but_preserves_policy(tmp_path):
    policy = PreviewPolicy(enabled=True, epoch=1, runtime_instance_id="i")
    write_policy(tmp_path, policy)
    for index in range(2):
        assert commit_preview(
            tmp_path,
            f"frame{index}".encode(),
            PreviewMeta(
                captured_at=f"t{index}", runtime_instance_id="i", policy_epoch=1
            ),
            policy,
        )
    assert len(list(tmp_path.glob("frame_*.jpg"))) == 2
    clear_preview(tmp_path)
    assert list(tmp_path.glob("*.jpg")) == []
    assert read_meta(tmp_path) is None
    assert read_policy(tmp_path) == policy


@pytest.mark.parametrize("duplicate", [False, True])
def test_metadata_failure_leaves_only_the_previous_selected_frame(
    tmp_path, monkeypatch, duplicate
):
    from cbrowser import preview

    policy = PreviewPolicy(enabled=True, epoch=1, runtime_instance_id="i")
    write_policy(tmp_path, policy)
    first = PreviewMeta(captured_at="first", runtime_instance_id="i", policy_epoch=1)
    assert commit_preview(tmp_path, b"first", first, policy)
    selected = preview.frame_path(tmp_path, read_meta(tmp_path))
    original = preview._atomic_write

    def failing(path, payload, **kwargs):
        if path.name == "meta.json":
            raise OSError("metadata unavailable")
        return original(path, payload, **kwargs)

    monkeypatch.setattr(preview, "_atomic_write", failing)
    for index in range(3):
        meta = first.model_copy(
            update={"captured_at": "first" if duplicate else f"failed-{index}"}
        )
        with pytest.raises(OSError):
            commit_preview(tmp_path, b"first" if duplicate else b"failed", meta, policy)
        assert list(tmp_path.glob("*.jpg")) == [selected]
        assert selected.read_bytes() == b"first"
        assert read_meta(tmp_path) == first


def test_success_collects_expired_legacy_and_unselected_frames(tmp_path):
    import os

    policy = PreviewPolicy(enabled=True, epoch=1, runtime_instance_id="i")
    write_policy(tmp_path, policy)
    old = tmp_path / "latest.jpg"
    old.write_bytes(b"private old frame")
    os.utime(old, (1, 1))
    assert commit_preview(
        tmp_path,
        b"new",
        PreviewMeta(captured_at="now", runtime_instance_id="i", policy_epoch=1),
        policy,
    )
    assert not old.exists()


@pytest.mark.parametrize(
    "enabled,epoch,instance,expected",
    [
        (True, 2, "i", True),
        (False, 2, "i", False),
        (True, 3, "i", False),
        (True, 2, "other", False),
    ],
)
def test_snapshot_reader_fences_policy_epoch_and_instance(
    tmp_path, enabled, epoch, instance, expected
):
    from cbrowser.preview import read_preview

    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="i")
    write_policy(tmp_path, policy)
    assert read_preview(tmp_path, policy, epoch=2, runtime_instance_id="i") is None
    meta = PreviewMeta(captured_at="t", runtime_instance_id="i", policy_epoch=2)
    assert commit_preview(tmp_path, b"frame", meta, policy)
    live = policy.model_copy(update={"enabled": enabled})
    snapshot = read_preview(tmp_path, live, epoch=epoch, runtime_instance_id=instance)
    assert (snapshot is not None) is expected
    if expected:
        assert snapshot == (meta, b"frame")
