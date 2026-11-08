from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from cbrowser.preview import (
    CAPTURE_INTERVAL_SEC,
    JPEG_QUALITY,
    PREVIEW_WIDTH,
    PreviewMeta,
    PreviewPolicy,
    capture_screenshot_params,
    clear_preview,
    commit_preview,
    is_current_preview,
    preview_dir,
    read_meta,
    read_policy,
    write_policy,
)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_preview_dir_is_isolated_from_user_data(tmp_path: Path) -> None:
    assert preview_dir(tmp_path, "p1") == tmp_path / "profiles" / "p1" / "preview"
    assert preview_dir(tmp_path, "p1") != tmp_path / "profiles" / "p1" / "profile" / "preview"


def test_policy_roundtrip_is_atomic_and_private(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=3, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    assert read_policy(directory) == policy
    assert mode(directory / "policy.json") == 0o600


def test_policy_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_policy(preview_dir(tmp_path, "p1")) is None


def test_commit_preview_writes_private_jpeg_and_meta(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at="2026-11-07T12:00:00+00:00",
        runtime_instance_id="inst-1",
        policy_epoch=2,
    )
    assert commit_preview(directory, b"\xff\xd8jpeg", meta, policy) is True
    assert (directory / "latest.jpg").read_bytes() == b"\xff\xd8jpeg"
    assert mode(directory / "latest.jpg") == 0o600
    assert mode(directory / "meta.json") == 0o600
    assert read_meta(directory) == meta


def test_commit_preview_rejects_disabled_policy(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at="2026-11-07T12:00:00+00:00",
        runtime_instance_id="inst-1",
        policy_epoch=2,
    )
    write_policy(
        directory,
        PreviewPolicy(enabled=False, epoch=3, runtime_instance_id="inst-1"),
    )
    assert commit_preview(directory, b"\xff\xd8jpeg", meta, policy) is False
    assert not (directory / "latest.jpg").exists()
    assert read_meta(directory) is None


def test_commit_preview_rejects_stale_epoch_notification(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at="2026-11-07T12:00:00+00:00",
        runtime_instance_id="inst-1",
        policy_epoch=2,
    )
    write_policy(
        directory,
        PreviewPolicy(enabled=True, epoch=3, runtime_instance_id="inst-1"),
    )
    assert commit_preview(directory, b"\xff\xd8jpeg", meta, policy) is False
    assert not (directory / "latest.jpg").exists()


def test_commit_preview_rejects_old_instance_after_reset(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at="2026-11-07T12:00:00+00:00",
        runtime_instance_id="inst-1",
        policy_epoch=2,
    )
    write_policy(
        directory,
        PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst-2"),
    )
    assert commit_preview(directory, b"\xff\xd8jpeg", meta, policy) is False
    assert not (directory / "latest.jpg").exists()


def test_clear_preview_removes_image_meta_keeps_policy(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at="2026-11-07T12:00:00+00:00",
        runtime_instance_id="inst-1",
        policy_epoch=2,
    )
    assert commit_preview(directory, b"\xff\xd8jpeg", meta, policy)
    clear_preview(directory)
    assert not (directory / "latest.jpg").exists()
    assert not (directory / "meta.json").exists()
    assert read_policy(directory) == policy


def test_is_current_preview_matrix(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at="2026-11-07T12:00:00+00:00",
        runtime_instance_id="inst-1",
        policy_epoch=2,
    )
    assert commit_preview(directory, b"\xff\xd8jpeg", meta, policy)
    assert is_current_preview(directory, policy, epoch=2, runtime_instance_id="inst-1")
    assert not is_current_preview(
        directory, policy, epoch=3, runtime_instance_id="inst-1"
    )
    assert not is_current_preview(
        directory, policy, epoch=2, runtime_instance_id="inst-2"
    )
    disabled = PreviewPolicy(enabled=False, epoch=2, runtime_instance_id="inst-1")
    write_policy(directory, disabled)
    assert not is_current_preview(
        directory, disabled, epoch=2, runtime_instance_id="inst-1"
    )


def test_is_current_preview_requires_meta(tmp_path: Path) -> None:
    directory = preview_dir(tmp_path, "p1")
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    assert not is_current_preview(
        directory, policy, epoch=2, runtime_instance_id="inst-1"
    )


def test_capture_screenshot_params_scale_to_width() -> None:
    params = capture_screenshot_params(1920, 1080)
    assert params["format"] == "jpeg"
    assert params["quality"] == JPEG_QUALITY
    assert params["clip"]["width"] == 1920
    assert round(params["clip"]["width"] * params["clip"]["scale"]) == PREVIEW_WIDTH
    assert CAPTURE_INTERVAL_SEC == 15.0


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
