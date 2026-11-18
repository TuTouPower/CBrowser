"""t080: host-to-volume storage migration — plan, journal, fault paths."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cbrowser.supervisor.storage_migration import (
    MigrationError,
    MigrationRunner,
    WriterActiveError,
    build_plan,
    verify_restore_point,
)


def _write(root: Path, rel: str, content: bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture()
def source_tree(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "legacy-data"
    fonts = tmp_path / "legacy-fonts"
    _write(data, "profiles/p1/profile/Preferences", b"prefs")
    _write(data, "runtime/p1/x11/X99", b"socket-bytes")
    _write(data, "runtime/.secrets/p1/proxy_credentials.json", b"{}")
    _write(data, "control/gates/p1/inst/role/policy.json", b"{}")
    _write(data, "control/events-cursor.json", b"7")
    _write(data, "engine-cache/geoip/db.mmdb", b"geoip")
    _write(data, "profiles/p1/profile/SingletonLock", b"skip-me")
    _write(fonts, "windows/set1/font.ttf", b"font-bytes")
    return data, fonts


@pytest.fixture()
def restore_point(tmp_path: Path, source_tree: tuple[Path, Path]) -> Path:
    data, _fonts = source_tree
    point = tmp_path / "point"
    prefs = data / "profiles/p1/profile/Preferences"
    db_bytes = b"fake-db"
    _write(point, "db/cbrowser.db", db_bytes)
    _write(point, "profiles/p1/profile/Preferences", prefs.read_bytes())
    manifest = {
        "format": 1,
        "kind": "cbrowser-restore-point",
        "data_root": str(data),
        "db": {
            "file": "db/cbrowser.db",
            "sha256": _sha(db_bytes),
            "size": len(db_bytes),
        },
        "profiles": [
            {
                "id": "p1",
                "dir": "profiles/p1/profile",
                "files": {
                    "Preferences": {
                        "sha256": _sha(prefs.read_bytes()),
                        "size": prefs.stat().st_size,
                    }
                },
            }
        ],
    }
    (point / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return point


def _runner(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
    **overrides: object,
) -> MigrationRunner:
    data, fonts = source_tree
    plan = build_plan(data, fonts)
    targets = {
        "data": tmp_path / "vol-data",
        "fonts": tmp_path / "vol-fonts",
        "runtime": tmp_path / "vol-runtime",
    }
    kwargs: dict = {
        "plan": plan,
        "targets": targets,
        "journal_path": tmp_path / "journal.json",
        "restore_point": restore_point,
        "writer_detector": lambda roots: [],
    }
    kwargs.update(overrides)
    return MigrationRunner(**kwargs)


def test_plan_classification(source_tree: tuple[Path, Path]) -> None:
    data, fonts = source_tree
    plan = build_plan(data, fonts)
    by_target = {(r.target_kind, r.target_rel) for r in plan.records}
    assert ("data", "profiles/p1/profile/Preferences") in by_target
    assert ("data", "control/events-cursor.json") in by_target
    assert ("data", "engine-cache/geoip/db.mmdb") in by_target
    assert ("runtime", "p1/x11/X99") in by_target
    assert ("runtime", ".secrets/p1/proxy_credentials.json") in by_target
    assert ("runtime", "gates/p1/inst/role/policy.json") in by_target
    assert ("fonts", "windows/set1/font.ttf") in by_target
    # Singleton rendezvous files never migrate.
    assert not any("SingletonLock" in r.source_rel for r in plan.records)
    assert plan.total_bytes == sum(r.size for r in plan.records)


def test_plan_rejects_symlinks(tmp_path: Path) -> None:
    data = tmp_path / "d"
    fonts = tmp_path / "f"
    _write(data, "profiles/p1/profile/real", b"x")
    (data / "profiles/p1/profile/link").symlink_to("real")
    with pytest.raises(MigrationError):
        build_plan(data, fonts)


def test_verify_restore_point_detects_tampering(
    restore_point: Path,
) -> None:
    verify_restore_point(restore_point)
    (restore_point / "db/cbrowser.db").write_bytes(b"tampered")
    with pytest.raises(MigrationError):
        verify_restore_point(restore_point)


def test_run_happy_path(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    runner = _runner(tmp_path, source_tree, restore_point)
    assert runner.run() == "done"
    targets = runner.targets
    assert (targets["data"] / "profiles/p1/profile/Preferences").read_bytes() == b"prefs"
    assert (targets["runtime"] / "p1/x11/X99").read_bytes() == b"socket-bytes"
    assert (
        targets["runtime"] / "gates/p1/inst/role/policy.json"
    ).read_bytes() == b"{}"
    assert (targets["fonts"] / "windows/set1/font.ttf").read_bytes() == b"font-bytes"
    # Source untouched; staging cleaned; re-run is a no-op.
    data, _fonts = source_tree
    assert (data / "profiles/p1/profile/Preferences").read_bytes() == b"prefs"
    assert not list(targets["data"].glob(".migration-staging-*"))
    assert runner.run() == "done"


def test_run_refuses_writers(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    runner = _runner(
        tmp_path,
        source_tree,
        restore_point,
        writer_detector=lambda roots: ["pid 42 (chrome)"],
    )
    with pytest.raises(WriterActiveError):
        runner.run()
    assert not (tmp_path / "vol-data/profiles").exists()


def test_run_requires_confirmed_stop_when_detection_unavailable(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    runner = _runner(
        tmp_path,
        source_tree,
        restore_point,
        writer_detector=lambda roots: None,
    )
    with pytest.raises(MigrationError):
        runner.run()
    runner2 = _runner(
        tmp_path,
        source_tree,
        restore_point,
        writer_detector=lambda roots: None,
        confirm_stack_stopped=True,
    )
    assert runner2.run() == "done"


def test_run_requires_verified_restore_point(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    (restore_point / "profiles/p1/profile/Preferences").write_bytes(b"tampered")
    runner = _runner(tmp_path, source_tree, restore_point)
    with pytest.raises(MigrationError):
        runner.run()
    assert not (tmp_path / "vol-data/profiles").exists()


def test_run_resumes_after_copy_fault(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner(tmp_path, source_tree, restore_point)
    original = runner._copy_file
    calls = {"count": 0}

    def flaky(source: Path, destination: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("injected copy fault")
        original(source, destination)

    monkeypatch.setattr(runner, "_copy_file", flaky)
    with pytest.raises(OSError):
        runner.run()
    monkeypatch.setattr(runner, "_copy_file", original)
    assert runner.run() == "done"
    assert (runner.targets["fonts"] / "windows/set1/font.ttf").exists()


def test_run_refuses_conflicting_target_content(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    runner = _runner(tmp_path, source_tree, restore_point)
    _write(runner.targets["data"], "profiles/p1/profile/Preferences", b"other")
    with pytest.raises(MigrationError):
        runner.run()


def test_rollback_removes_only_placed_files(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    runner = _runner(tmp_path, source_tree, restore_point)
    adopted = _write(
        runner.targets["fonts"], "windows/set1/font.ttf", b"font-bytes"
    )
    assert runner.run() == "done"
    placed = runner.targets["data"] / "profiles/p1/profile/Preferences"
    assert placed.exists()
    assert runner.rollback() == "rolled_back"
    assert not placed.exists()
    # The pre-existing identical file was adopted, not placed: it stays.
    assert adopted.exists()


# --- review round 1 fixes (t080_code_f002..f006) -------------------------


def test_build_plan_refuses_missing_source_roots(
    tmp_path: Path, source_tree: tuple[Path, Path]
) -> None:
    data, fonts = source_tree
    with pytest.raises(MigrationError):
        build_plan(tmp_path / "missing-data", fonts)
    with pytest.raises(MigrationError):
        build_plan(data, tmp_path / "missing-fonts")


def test_detect_writers_treats_lsof_failure_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess as sp

    from cbrowser.supervisor import storage_migration as sm

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(sm.shutil, "which", lambda _: "/usr/bin/lsof")
    monkeypatch.setattr(
        sm.subprocess, "run", lambda *a, **k: Result(2, "", "lsof: failed")
    )
    assert sm.detect_writers([tmp_path]) is None
    monkeypatch.setattr(
        sm.subprocess, "run", lambda *a, **k: Result(1, "", "lsof: warning")
    )
    assert sm.detect_writers([tmp_path]) is None
    monkeypatch.setattr(sm.subprocess, "run", lambda *a, **k: Result(1, "", ""))
    assert sm.detect_writers([tmp_path]) == []
    monkeypatch.setattr(
        sm.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(sp.TimeoutExpired("lsof", 120)),
    )
    assert sm.detect_writers([tmp_path]) is None


def _stamp(target: Path, volume: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / ".cbrowser-volume.json").write_text(
        json.dumps({"volume": volume, "prefix": "cbrowser"}), encoding="utf-8"
    )


def test_run_refuses_target_volume_ownership_mismatch(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    runner = _runner(
        tmp_path, source_tree, restore_point, expected_prefix="cbrowser"
    )
    with pytest.raises(MigrationError):
        runner.run()
    for kind in ("data", "fonts", "runtime"):
        _stamp(runner.targets[kind], f"other-{kind}")
    runner = _runner(
        tmp_path, source_tree, restore_point, expected_prefix="cbrowser"
    )
    with pytest.raises(MigrationError):
        runner.run()
    for kind in ("data", "fonts", "runtime"):
        _stamp(runner.targets[kind], f"cbrowser-{kind}")
    runner = _runner(
        tmp_path, source_tree, restore_point, expected_prefix="cbrowser"
    )
    assert runner.run() == "done"


def test_run_refuses_restore_point_from_another_data_root(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    # A restore point taken from a DIFFERENT deployment: internally
    # consistent (it verifies on its own), but its recorded Profile
    # file digests do not match this source tree (t080 f003/f009).
    foreign = tmp_path / "foreign-point"
    foreign_prefs = b"foreign-prefs"
    _write(foreign, "db/cbrowser.db", b"fake-db")
    _write(foreign, "profiles/p1/profile/Preferences", foreign_prefs)
    manifest = {
        "format": 1,
        "kind": "cbrowser-restore-point",
        "data_root": "/data",
        "db": {
            "file": "db/cbrowser.db",
            "sha256": _sha(b"fake-db"),
            "size": len(b"fake-db"),
        },
        "profiles": [
            {
                "id": "p1",
                "dir": "profiles/p1/profile",
                "files": {
                    "Preferences": {
                        "sha256": _sha(foreign_prefs),
                        "size": len(foreign_prefs),
                    }
                },
            }
        ],
    }
    (foreign / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    runner = _runner(tmp_path, source_tree, foreign)
    with pytest.raises(MigrationError):
        runner.run()


def test_cli_style_rollback_adopts_journal_identity(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    from cbrowser.supervisor.storage_migration import MigrationPlan

    runner = _runner(tmp_path, source_tree, restore_point)
    assert runner.run() == "done"
    journal_path = tmp_path / "journal.json"
    before = json.loads(journal_path.read_text(encoding="utf-8"))
    # Staging residue under the ORIGINAL run_id (e.g. crash mid-switch).
    residue = (
        runner.targets["data"] / f".migration-staging-{before['run_id']}" / "x"
    )
    residue.parent.mkdir(parents=True)
    residue.write_bytes(b"residue")
    placed = runner.targets["data"] / "profiles/p1/profile/Preferences"
    assert placed.exists()

    cli_runner = MigrationRunner(
        plan=MigrationPlan.empty(),
        targets=runner.targets,
        journal_path=journal_path,
    )
    assert cli_runner.rollback() == "rolled_back"
    assert not placed.exists()
    assert not residue.parent.exists()
    after = json.loads(journal_path.read_text(encoding="utf-8"))
    assert after["run_id"] == before["run_id"]
    assert after["plan_digest"] == before["plan_digest"]
    assert after["total_bytes"] == before["total_bytes"]
    assert after["phase"] == "rolled_back"


def test_migration_preserves_empty_directories_and_modes(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    import os

    data, fonts = source_tree
    empty = data / "artifacts" / "p1" / "empty-dir"
    empty.mkdir(parents=True)
    os.chmod(empty, 0o751)
    font_empty = fonts / "windows" / "set2"
    font_empty.mkdir(parents=True)
    os.chmod(font_empty, 0o755)

    runner = _runner(tmp_path, source_tree, restore_point)
    assert runner.run() == "done"
    target_empty = runner.targets["data"] / "artifacts/p1/empty-dir"
    assert target_empty.is_dir()
    assert target_empty.stat().st_mode & 0o777 == 0o751
    target_font_empty = runner.targets["fonts"] / "windows/set2"
    assert target_font_empty.is_dir()
    assert target_font_empty.stat().st_mode & 0o777 == 0o755


def test_run_after_rollback_starts_over_and_completes(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    # t080 f007: rolled_back is a restartable terminal state, not a
    # silent no-op success.
    runner = _runner(tmp_path, source_tree, restore_point)
    assert runner.run() == "done"
    assert runner.rollback() == "rolled_back"
    placed = runner.targets["data"] / "profiles/p1/profile/Preferences"
    assert not placed.exists()
    runner2 = _runner(tmp_path, source_tree, restore_point)
    assert runner2.run() == "done"
    assert placed.exists()


def test_rollback_after_switch_failure_removes_created_directories(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    # t080 f008: directories created by _switch are journaled before
    # the first file placement, so a refused switch still rolls back
    # the (empty) directories it created.
    data, _fonts = source_tree
    (data / "artifacts" / "p1" / "empty-dir").mkdir(parents=True)
    runner = _runner(tmp_path, source_tree, restore_point)
    _write(runner.targets["data"], "profiles/p1/profile/Preferences", b"other")
    with pytest.raises(MigrationError):
        runner.run()
    created = runner.targets["data"] / "artifacts/p1/empty-dir"
    assert created.is_dir()
    assert runner.rollback() == "rolled_back"
    assert not created.exists()


def test_done_journal_refuses_a_different_plan(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    # t080 f010: the done shortcut must not bypass plan identity.
    runner = _runner(tmp_path, source_tree, restore_point)
    assert runner.run() == "done"
    journal_path = tmp_path / "journal.json"
    before = journal_path.read_bytes()
    data, fonts = source_tree
    _write(data, "profiles/p2/profile/Preferences", b"p2-prefs")
    runner2 = _runner(tmp_path, source_tree, restore_point)
    with pytest.raises(MigrationError):
        runner2.run()
    assert journal_path.read_bytes() == before


def _point_with_profiles(tmp_path: Path, profiles: list[dict]) -> Path:
    point = tmp_path / "custom-point"
    db_bytes = b"fake-db"
    _write(point, "db/cbrowser.db", db_bytes)
    manifest = {
        "format": 1,
        "kind": "cbrowser-restore-point",
        "data_root": "/data",
        "db": {
            "file": "db/cbrowser.db",
            "sha256": _sha(db_bytes),
            "size": len(db_bytes),
        },
        "profiles": profiles,
    }
    (point / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return point


def test_run_refuses_zero_profile_restore_point_for_profile_source(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    # t080 f011: a self-consistent point covering no Profile at all
    # must not stand in for a source that has Profiles.
    point = _point_with_profiles(tmp_path, [])
    runner = _runner(tmp_path, source_tree, point)
    with pytest.raises(MigrationError):
        runner.run()


def test_run_refuses_subset_restore_point(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
) -> None:
    # t080 f011: source has p1+p2; the (fixture) point covers only p1.
    data, _fonts = source_tree
    _write(data, "profiles/p2/profile/Preferences", b"p2-prefs")
    runner = _runner(tmp_path, source_tree, restore_point)
    with pytest.raises(MigrationError):
        runner.run()


def test_run_refuses_when_target_capacity_insufficient(
    tmp_path: Path,
    source_tree: tuple[Path, Path],
    restore_point: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC-004: insufficient capacity fails before any file is placed
    # (t080_test_f002).
    import shutil as _shutil
    from collections import namedtuple

    from cbrowser.supervisor import storage_migration as sm

    Usage = namedtuple("usage", ["total", "used", "free"])
    monkeypatch.setattr(
        sm.shutil, "disk_usage", lambda _p: Usage(100, 100, 0)
    )
    runner = _runner(tmp_path, source_tree, restore_point)
    with pytest.raises(MigrationError):
        runner.run()
    assert not (
        runner.targets["data"] / "profiles/p1/profile/Preferences"
    ).exists()


def test_inventory_dry_run_changes_nothing(
    tmp_path: Path, source_tree: tuple[Path, Path]
) -> None:
    # AC-004: the dry-run (build_plan / CLI inventory) must not modify
    # the source trees and must not create targets or journals
    # (t080_test_f002).
    import subprocess
    import sys

    data, fonts = source_tree

    def snapshot(root: Path) -> dict[str, str]:
        return {
            p.relative_to(root).as_posix(): _sha(p.read_bytes())
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }

    before = (snapshot(data), snapshot(fonts))
    plan = build_plan(data, fonts)
    assert plan.records
    assert (snapshot(data), snapshot(fonts)) == before

    script = Path(__file__).resolve().parents[2] / "scripts" / "storage_migration.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "inventory",
            "--source-data-root",
            str(data),
            "--source-fonts-dir",
            str(fonts),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["files"] == len(plan.records)
    assert (snapshot(data), snapshot(fonts)) == before
