"""t066: environment restore points (scripts/restore_point.py).

Covers AC-009 (complete set: DB + Profile state/config + credential
prerequisites), AC-010 (corruption / space / validation / interruption
at set-switch points) against a fabricated live environment with a real
migrated database.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "restore_point.py"
_spec = importlib.util.spec_from_file_location("restore_point", _SCRIPT)
assert _spec is not None and _spec.loader is not None
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)


def _make_live(tmp_path: Path) -> dict:
    data_root = tmp_path / "data"
    profile_dir = data_root / "profiles" / "p1" / "profile"
    (profile_dir / "Default").mkdir(parents=True)
    (profile_dir / "Default" / "Cookies").write_bytes(b"cookie-v1")
    (profile_dir / "Default" / "Preferences").write_text("{}", encoding="utf-8")
    (profile_dir / "Local State").write_text('{"x": 1}', encoding="utf-8")
    db_dir = tmp_path / "dbvol"
    db_dir.mkdir()
    db_path = db_dir / "cbrowser.db"
    run_database_migrations(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO profiles (id, display_number, name, fingerprint_seed,"
            " user_data_dir, current_config_version, created_at, updated_at)"
            " VALUES ('p1', 1, 'One', 123456, ?, 3,"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
            (str(profile_dir),),
        )
        connection.execute(
            "INSERT INTO profiles (id, display_number, name, fingerprint_seed,"
            " user_data_dir, current_config_version, created_at, updated_at)"
            " VALUES ('p2', 2, 'Two', 234567, ?, 1,"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
            (str(data_root / "profiles" / "p2" / "profile"),),
        )
        for pid in ("p1", "p2"):
            connection.execute(
                "INSERT INTO profile_runtimes (profile_id, desired_state,"
                " observed_state, runtime_instance_id, updated_at)"
                " VALUES (?, 'stopped', 'stopped', NULL, '2026-01-01T00:00:00+00:00')",
                (pid,),
            )
        connection.commit()
    finally:
        connection.close()
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "admin_password").write_text("do-not-copy-me", encoding="utf-8")
    (secrets_dir / "supervisor_key").write_text("also-secret", encoding="utf-8")
    return {
        "data_root": data_root,
        "profile_dir": profile_dir,
        "db_path": db_path,
        "secrets_dir": secrets_dir,
        "point": tmp_path / "points" / "point-1",
    }


def _create(env: dict) -> int:
    return rp.main(
        [
            "create",
            "--db",
            str(env["db_path"]),
            "--data-root",
            str(env["data_root"]),
            "--out",
            str(env["point"]),
            "--secrets-dir",
            str(env["secrets_dir"]),
            "--label",
            "test-point",
        ]
    )


def _restore(env: dict, db_path: Path | None = None) -> int:
    return rp.main(
        [
            "restore",
            "--point",
            str(env["point"]),
            "--db",
            str(db_path or env["db_path"]),
            "--data-root",
            str(env["data_root"]),
        ]
    )


def _set_seed(db_path: Path, seed: int) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE profiles SET fingerprint_seed = ? WHERE id = 'p1'", (seed,)
        )
        connection.commit()
    finally:
        connection.close()


def _seed(db_path: Path) -> int:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return int(
            connection.execute(
                "SELECT fingerprint_seed FROM profiles WHERE id = 'p1'"
            ).fetchone()[0]
        )
    finally:
        connection.close()


def _set_config_version(db_path: Path, version: int) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE profiles SET current_config_version = ? WHERE id = 'p1'",
            (version,),
        )
        connection.commit()
    finally:
        connection.close()


def _config_version(db_path: Path) -> int:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return int(
            connection.execute(
                "SELECT current_config_version FROM profiles WHERE id = 'p1'"
            ).fetchone()[0]
        )
    finally:
        connection.close()


def test_create_verify_and_manifest_contract(tmp_path: Path) -> None:
    env = _make_live(tmp_path)
    assert _create(env) == 0
    assert rp.main(["verify", "--point", str(env["point"])]) == 0
    manifest = json.loads((env["point"] / "manifest.json").read_text())
    assert manifest["db"]["integrity"] == "ok"
    assert manifest["db"]["schema_stamp"] == rp._schema_stamp(env["db_path"])
    by_id = {p["id"]: p for p in manifest["profiles"]}
    assert by_id["p1"]["config_version"] == 3
    assert by_id["p1"]["dir"] == "profiles/p1/profile"
    assert by_id["p2"]["dir"] is None
    assert [c["name"] for c in manifest["credential_prerequisites"]] == [
        "admin_password",
        "supervisor_key",
    ]
    # Credential contents never enter the restore point.
    for path in env["point"].rglob("*"):
        if path.is_file():
            assert b"do-not-copy-me" not in path.read_bytes()
            assert b"also-secret" not in path.read_bytes()


def test_create_refuses_actual_writer(tmp_path: Path) -> None:
    env = _make_live(tmp_path)
    connection = sqlite3.connect(env["db_path"])
    connection.execute(
        "UPDATE profile_runtimes SET runtime_instance_id = 'inst-1'"
        " WHERE profile_id = 'p1'"
    )
    connection.commit()
    connection.close()
    assert _create(env) == 2
    assert not env["point"].exists()
    connection = sqlite3.connect(env["db_path"])
    connection.execute(
        "UPDATE profile_runtimes SET runtime_instance_id = NULL,"
        " desired_state = 'running' WHERE profile_id = 'p1'"
    )
    connection.commit()
    connection.close()
    assert _create(env) == 2
    assert not env["point"].exists()


def test_restore_roundtrip_returns_to_point_state(tmp_path: Path) -> None:
    env = _make_live(tmp_path)
    assert _create(env) == 0
    # Mutate the live environment after the point was taken: browser
    # state bytes, profile config version and seed all diverge.
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")
    (env["profile_dir"] / "Default" / "Preferences").write_text(
        '{"mutated": true}', encoding="utf-8"
    )
    _set_seed(env["db_path"], 999999)
    _set_config_version(env["db_path"], 7)
    assert _restore(env) == 0
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v1"
    assert (
        env["profile_dir"] / "Default" / "Preferences"
    ).read_text(encoding="utf-8") == "{}"
    assert _seed(env["db_path"]) == 123456
    assert _config_version(env["db_path"]) == 3
    # The pre-restore set is retained, not deleted (the glob also sees
    # the retained -wal/-shm sidecars of the previous database).
    retained = [
        p
        for p in env["db_path"].parent.glob("cbrowser.db.pre-restore-*")
        if not p.name.endswith(("-wal", "-shm"))
    ]
    assert len(retained) == 1
    assert _seed(retained[0]) == 999999


def test_restore_refuses_corrupt_profile_payload(tmp_path: Path) -> None:
    env = _make_live(tmp_path)
    assert _create(env) == 0
    target = env["point"] / "profiles" / "p1" / "profile" / "Default" / "Cookies"
    target.write_bytes(b"tampered!")
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")
    assert _restore(env) == 1
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v2"


def test_restore_refuses_corrupt_point_database(tmp_path: Path) -> None:
    # The corruption is caught by the manifest sha256 comparison,
    # which runs before PRAGMA integrity_check in validate_point; the
    # integrity branch is defence in depth behind it (a sha256-matching
    # but integrity-failing database is not constructible through the
    # point format, so it has no separate case).
    env = _make_live(tmp_path)
    assert _create(env) == 0
    point_db = env["point"] / "db" / "cbrowser.db"
    with point_db.open("r+b") as handle:
        handle.seek(100)
        handle.write(b"GARBAGE")
    assert _restore(env) == 1
    assert _seed(env["db_path"]) == 123456


def test_restore_refuses_schema_stamp_mismatch(tmp_path: Path) -> None:
    env = _make_live(tmp_path)
    assert _create(env) == 0
    connection = sqlite3.connect(env["db_path"])
    connection.execute("UPDATE alembic_version SET version_num = 'deadbeef0000'")
    connection.commit()
    connection.close()
    assert _restore(env) == 1


def test_restore_refuses_insufficient_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _make_live(tmp_path)
    assert _create(env) == 0
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")

    class _Usage:
        total = 10**12
        used = 10**12
        free = 0

    monkeypatch.setattr(rp.shutil, "disk_usage", lambda _p: _Usage())
    assert _restore(env) == 1
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v2"


def test_restore_removes_dir_absent_from_point(tmp_path: Path) -> None:
    env = _make_live(tmp_path)
    assert _create(env) == 0
    late_dir = env["data_root"] / "profiles" / "p2" / "profile"
    late_dir.mkdir(parents=True)
    (late_dir / "Default").mkdir()
    (late_dir / "Default" / "Cookies").write_bytes(b"late-state")
    assert _restore(env) == 0
    assert not late_dir.exists()
    retained = list((env["data_root"] / "profiles" / "p2").glob(".pre-restore-*"))
    assert len(retained) == 1
    assert (retained[0] / "Default" / "Cookies").read_bytes() == b"late-state"


def test_restore_into_empty_site(tmp_path: Path) -> None:
    env = _make_live(tmp_path)
    assert _create(env) == 0
    shutil.rmtree(env["data_root"])
    env["db_path"].unlink()
    assert _restore(env) == 0
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v1"
    assert _seed(env["db_path"]) == 123456


def test_interrupted_switch_rolls_back_then_rerun_completes(
    tmp_path: Path,
) -> None:
    env = _make_live(tmp_path)
    assert _create(env) == 0
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")
    _set_seed(env["db_path"], 999999)
    # Fabricate the exact state a crash mid-switch leaves: the profile
    # item's live dir was moved aside, its staged copy is in place, and
    # the journal still says "pending".
    data_root = env["data_root"]
    journal_path = data_root / ".restore-journal.json"
    switch_id = "crashswitch1"
    live_dir = env["profile_dir"]
    previous_dir = live_dir.with_name(f".pre-restore-{switch_id}")
    staged_dir = live_dir.with_name(f".restore-staging-{switch_id}")
    shutil.copytree(env["point"] / "profiles" / "p1" / "profile", staged_dir)
    live_dir.replace(previous_dir)
    journal = {
        "version": 1,
        "switch_id": switch_id,
        "phase": "switching",
        "point": str(env["point"]),
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "items": [
            {
                "kind": "profile",
                "id": "p1",
                "live_path": str(live_dir),
                "staged_path": str(staged_dir),
                "previous_path": str(previous_dir),
                "state": "pending",
                "sidecars": False,
            }
        ],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    # First run performs the rollback and stops.
    assert _restore(env) == 3
    assert (live_dir / "Default" / "Cookies").read_bytes() == b"cookie-v2"
    assert _seed(env["db_path"]) == 999999
    # Second run completes the restore.
    assert _restore(env) == 0
    assert (live_dir / "Default" / "Cookies").read_bytes() == b"cookie-v1"
    assert _seed(env["db_path"]) == 123456


def test_restore_refuses_tampered_manifest_format_or_kind(
    tmp_path: Path,
) -> None:
    env = _make_live(tmp_path)
    assert _create(env) == 0
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")
    manifest_path = env["point"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["format"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert _restore(env) == 1
    manifest["format"] = 1
    manifest["kind"] = "tampered-kind"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert _restore(env) == 1
    # Neither refusal touched the live environment.
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v2"
    assert _seed(env["db_path"]) == 123456


def test_restore_with_explicit_journal_inside_data_root(
    tmp_path: Path,
) -> None:
    """The deploy path passes --journal inside the data root (deploy.sh
    uses /data/restore-journal.json); that explicit branch must behave
    exactly like the default journal location."""
    env = _make_live(tmp_path)
    assert _create(env) == 0
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")
    _set_seed(env["db_path"], 999999)
    journal_path = env["data_root"] / "restore-journal.json"
    assert (
        rp.main(
            [
                "restore",
                "--point",
                str(env["point"]),
                "--db",
                str(env["db_path"]),
                "--data-root",
                str(env["data_root"]),
                "--journal",
                str(journal_path),
            ]
        )
        == 0
    )
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v1"
    assert _seed(env["db_path"]) == 123456
    # The journal landed at the explicit path (not the default one)
    # and records the completed switch.
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["phase"] == "complete"
    default_journal = env["data_root"] / ".restore-journal.json"
    assert not default_journal.exists()


def test_create_refuses_transitional_observed_state(tmp_path: Path) -> None:
    env = _make_live(tmp_path)
    connection = sqlite3.connect(env["db_path"])
    connection.execute(
        "UPDATE profile_runtimes SET observed_state = 'starting'"
        " WHERE profile_id = 'p1'"
    )
    connection.commit()
    connection.close()
    assert _create(env) == 2
    assert not env["point"].exists()


def test_restore_space_checks_are_per_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Insufficient space on the database volume and on the data root
    are independent refusals; each leaves the live set untouched."""
    env = _make_live(tmp_path)
    assert _create(env) == 0
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")
    _set_seed(env["db_path"], 999999)
    real_disk_usage = shutil.disk_usage

    class _Usage:
        def __init__(self, free: int) -> None:
            self.total = 10**12
            self.free = free
            self.used = self.total - free

    def fake_for(blocked: Path):
        def fake(path) -> _Usage:
            if Path(path).resolve() == blocked.resolve():
                return _Usage(0)
            return _Usage(real_disk_usage(path).free)

        return fake

    # Only the database volume is full.
    monkeypatch.setattr(
        rp.shutil, "disk_usage", fake_for(env["db_path"].parent)
    )
    assert _restore(env) == 1
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v2"
    assert _seed(env["db_path"]) == 999999
    # Only the data root is full.
    monkeypatch.setattr(rp.shutil, "disk_usage", fake_for(env["data_root"]))
    assert _restore(env) == 1
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v2"
    assert _seed(env["db_path"]) == 999999


def test_interrupted_mixed_switch_rolls_back_db_and_profile(
    tmp_path: Path,
) -> None:
    """Cross-media interruption (AC-010): the DB item already switched
    (old set, with its -wal/-shm sidecars, moved aside) while the
    profile item never started.  Rollback must restore the whole old
    set — DB file, sidecars and profile directory — with no version
    mismatch between the two media, and a re-run must then complete."""
    env = _make_live(tmp_path)
    assert _create(env) == 0
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")
    _set_seed(env["db_path"], 999999)
    db_path = env["db_path"]
    # The old database's sidecars as they stand when the switch begins.
    Path(str(db_path) + "-wal").write_bytes(b"old-wal")
    Path(str(db_path) + "-shm").write_bytes(b"old-shm")
    switch_id = "mixedcrash1"
    db_previous = db_path.with_name(f"cbrowser.db.pre-restore-{switch_id}")
    db_staged = db_path.with_name(f"cbrowser.db.restore-staging-{switch_id}")
    # Fabricate the forward switch of the DB item: live moved aside
    # (with sidecars), the restore point's copy landed at live.
    shutil.copyfile(db_path, db_previous)
    Path(str(db_path) + "-wal").replace(Path(str(db_previous) + "-wal"))
    Path(str(db_path) + "-shm").replace(Path(str(db_previous) + "-shm"))
    shutil.copyfile(env["point"] / "db" / "cbrowser.db", db_path)
    # The profile item staged its copy but never started switching.
    live_dir = env["profile_dir"]
    profile_previous = live_dir.with_name(f".pre-restore-{switch_id}")
    profile_staged = live_dir.with_name(f".restore-staging-{switch_id}")
    shutil.copytree(env["point"] / "profiles" / "p1" / "profile", profile_staged)
    data_root = env["data_root"]
    journal_path = data_root / ".restore-journal.json"
    journal = {
        "version": 1,
        "switch_id": switch_id,
        "phase": "switching",
        "point": str(env["point"]),
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "items": [
            {
                "kind": "db",
                "id": "control-db",
                "live_path": str(db_path),
                "staged_path": str(db_staged),
                "previous_path": str(db_previous),
                "state": "switched",
                "sidecars": True,
            },
            {
                "kind": "profile",
                "id": "p1",
                "live_path": str(live_dir),
                "staged_path": str(profile_staged),
                "previous_path": str(profile_previous),
                "state": "pending",
                "sidecars": False,
            },
        ],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    # First run rolls the whole set back and stops.
    assert _restore(env) == 3
    assert Path(str(db_path) + "-wal").read_bytes() == b"old-wal"
    assert Path(str(db_path) + "-shm").read_bytes() == b"old-shm"
    # The sentinel sidecars are fabrication aids; keep SQLite away
    # from their bytes for the value assertions below.
    Path(str(db_path) + "-wal").unlink()
    Path(str(db_path) + "-shm").unlink()
    assert _seed(db_path) == 999999
    assert (live_dir / "Default" / "Cookies").read_bytes() == b"cookie-v2"
    # Second run completes the restore on both media.
    assert _restore(env) == 0
    assert _seed(db_path) == 123456
    assert (live_dir / "Default" / "Cookies").read_bytes() == b"cookie-v1"


def test_create_aborts_when_writer_appears_during_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The writer check runs again after the directory copies: a
    profile that starts (or whose configuration moves) while its
    directory is being copied tears the single-moment guarantee, so
    the point is discarded instead of published (AC-009)."""
    original_copy = rp._copy_tree_manifest

    def run_scenario(sub: Path, mutate) -> dict:
        sub.mkdir()
        env = _make_live(sub)
        fired = {"done": False}

        def spying_copy(source, target):
            if not fired["done"]:
                fired["done"] = True
                mutate(env)
            return original_copy(source, target)

        monkeypatch.setattr(rp, "_copy_tree_manifest", spying_copy)
        return env

    def bind_instance(env: dict) -> None:
        connection = sqlite3.connect(env["db_path"])
        connection.execute(
            "UPDATE profile_runtimes SET runtime_instance_id = 'late'"
            " WHERE profile_id = 'p1'"
        )
        connection.commit()
        connection.close()

    def bump_version(env: dict) -> None:
        connection = sqlite3.connect(env["db_path"])
        connection.execute(
            "UPDATE profiles SET current_config_version = 99"
            " WHERE id = 'p1'"
        )
        connection.commit()
        connection.close()

    env = run_scenario(tmp_path / "writer", bind_instance)
    assert _create(env) == 2
    assert not env["point"].exists()
    env = run_scenario(tmp_path / "version", bump_version)
    assert _create(env) == 2
    assert not env["point"].exists()


def test_restore_sweeps_stale_staging_leftovers(tmp_path: Path) -> None:
    """A run killed during staging leaves .restore-staging-* debris
    its (never written) journal cannot resume; the next restore
    sweeps it, while the retained .pre-restore-* set stays."""
    env = _make_live(tmp_path)
    assert _create(env) == 0
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")
    stale_db = env["db_path"].with_name("cbrowser.db.restore-staging-deadbeef")
    stale_db.write_bytes(b"orphan")
    stale_dir = env["profile_dir"].parent / ".restore-staging-deadbeef"
    stale_dir.mkdir()
    (stale_dir / "junk").write_bytes(b"orphan")
    assert _restore(env) == 0
    assert not stale_db.exists()
    assert not stale_dir.exists()
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v1"
    retained = [
        p
        for p in env["db_path"].parent.glob("cbrowser.db.pre-restore-*")
        if not p.name.endswith(("-wal", "-shm"))
    ]
    assert len(retained) == 1


def test_restore_crash_after_db_switch_rolls_back_on_next_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash during the real switch (injected at the journal write
    that follows the DB item) leaves the journal one step behind the
    filesystem; the next invocation must detect the physically
    switched DB item, roll the whole set back, and a further run must
    complete the restore."""
    env = _make_live(tmp_path)
    assert _create(env) == 0
    (env["profile_dir"] / "Default" / "Cookies").write_bytes(b"cookie-v2")
    _set_seed(env["db_path"], 999999)
    original_write = rp._atomic_write_json
    calls = {"count": 0}

    def crashing_write(path, payload):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("simulated crash")
        return original_write(path, payload)

    monkeypatch.setattr(rp, "_atomic_write_json", crashing_write)
    with pytest.raises(RuntimeError, match="simulated crash"):
        rp.main(
            [
                "restore",
                "--point",
                str(env["point"]),
                "--db",
                str(env["db_path"]),
                "--data-root",
                str(env["data_root"]),
            ]
        )
    monkeypatch.undo()
    # The journal on disk still records the DB item as pending even
    # though its renames already landed.
    data_root = env["data_root"]
    journal_path = data_root / ".restore-journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["items"][0]["kind"] == "db"
    assert journal["items"][0]["state"] == "pending"
    # Next run rolls back to the old set and stops.
    assert _restore(env) == 3
    assert _seed(env["db_path"]) == 999999
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v2"
    # A further run completes the restore.
    assert _restore(env) == 0
    assert _seed(env["db_path"]) == 123456
    assert (env["profile_dir"] / "Default" / "Cookies").read_bytes() == b"cookie-v1"
