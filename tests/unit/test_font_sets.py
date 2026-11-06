"""Unit tests for content-addressed platform font sets (t041 AC-001/AC-002)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from cbrowser.font_sets import (
    DETECTION_FONTS,
    FONT_EXTENSIONS,
    check_font_set,
    compute_set_id,
    default_font_set,
    discover_font_files,
    get_font_set,
    import_font_set,
    list_font_sets,
)

CLI = Path(__file__).resolve().parents[2] / "scripts" / "import_font_set.py"


def _font_bytes(name: str) -> bytes:
    return b"FONTDATA:" + name.encode("utf-8") + b":" + bytes(range(64))


def _write_font(directory: Path, name: str, content: bytes | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(_font_bytes(name) if content is None else content)
    return path


def _make_source(base: Path, names: list[str]) -> Path:
    for name in names:
        _write_font(base, name)
    return base


def _import_fonts(
    root: Path,
    source_dirs: list[Path],
    *,
    platform: str = "windows",
    source_version: str = "win11-26H2",
    **kwargs,
) -> dict:
    return import_font_set(
        platform,
        [str(directory) for directory in source_dirs],
        source_version,
        root=str(root),
        **kwargs,
    )


def _snapshot(directory: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def test_compute_set_id_only_depends_on_content() -> None:
    entries = [
        ("b.ttf", hashlib.sha256(b"B").hexdigest()),
        ("a.ttf", hashlib.sha256(b"A").hexdigest()),
    ]
    expected = hashlib.sha256(
        b"a.ttf\0"
        + hashlib.sha256(b"A").hexdigest().encode("ascii")
        + b"b.ttf\0"
        + hashlib.sha256(b"B").hexdigest().encode("ascii")
    ).hexdigest()
    assert compute_set_id(entries) == expected
    assert compute_set_id(list(reversed(entries))) == expected
    assert len(compute_set_id(entries)) == 64


def test_same_content_reimport_is_idempotent(tmp_path: Path) -> None:
    source = _make_source(tmp_path / "src", ["arial.ttf", "times.ttf"])
    root = tmp_path / "fonts"
    first = _import_fonts(
        root,
        [source],
        source="iso-A",
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert first["created"] is True
    assert first["file_count"] == 2
    assert first["integrity"]["ok"] is True
    first_dir = Path(first["dir"])
    before = _snapshot(first_dir)

    second = _import_fonts(
        root,
        [source],
        source="iso-B",
        created_at="2030-06-01T12:00:00+00:00",
    )
    assert second["created"] is False
    assert second["set_id"] == first["set_id"]
    assert second["dir"] == first["dir"]
    assert _snapshot(first_dir) == before


def test_content_change_or_file_change_yields_new_set_id(tmp_path: Path) -> None:
    source = tmp_path / "src"
    _write_font(source, "arial.ttf")
    _write_font(source, "times.ttf")
    root = tmp_path / "fonts"
    base = _import_fonts(root, [source])

    _write_font(source, "arial.ttf", b"CHANGED" + _font_bytes("arial.ttf"))
    changed = _import_fonts(root, [source])
    assert changed["set_id"] != base["set_id"]

    _write_font(source, "verdana.ttf")
    added = _import_fonts(root, [source])
    assert added["set_id"] != changed["set_id"]

    (source / "verdana.ttf").unlink()
    (source / "times.ttf").unlink()
    removed = _import_fonts(root, [source])
    assert removed["set_id"] != added["set_id"]
    assert len({base["set_id"], changed["set_id"], added["set_id"], removed["set_id"]}) == 4


def test_manifest_sha256_and_exclusions(tmp_path: Path) -> None:
    source = tmp_path / "src"
    _write_font(source, "arial.ttf")
    _write_font(source, "times.ttc")
    _write_font(source, "cour.otf")
    _write_font(source, "symbol.otc")
    _write_font(source / "nested", "nested.ttf")
    _write_font(source, "legacy.fon")
    _write_font(source, ".hidden.ttf")
    _write_font(source, "~$temp.ttf")
    _write_font(source, "arial.ttf.tmp")
    _write_font(source, "notes.txt")
    root = tmp_path / "fonts"
    result = _import_fonts(root, [source])
    set_dir = Path(result["dir"])
    manifest = json.loads((set_dir / "manifest.json").read_text(encoding="utf-8"))

    assert FONT_EXTENSIONS == {".ttf", ".ttc", ".otf", ".otc"}
    assert {entry["name"] for entry in manifest["files"]} == {
        "arial.ttf",
        "times.ttc",
        "cour.otf",
        "symbol.otc",
        "nested.ttf",
    }
    for entry in manifest["files"]:
        assert len(entry["sha256"]) == 64
        assert entry["sha256"] == hashlib.sha256(
            (set_dir / entry["name"]).read_bytes()
        ).hexdigest()
    assert manifest["platform"] == "windows"
    assert manifest["source_version"] == "win11-26H2"
    assert datetime.fromisoformat(manifest["created_at"]).tzinfo is not None


def test_check_font_set_problem_fields(tmp_path: Path) -> None:
    source = _make_source(tmp_path / "src", ["arial.ttf", "times.ttf"])
    root = tmp_path / "fonts"
    base_dir = Path(_import_fonts(root, [source])["dir"])
    assert check_font_set(base_dir)["ok"] is True

    tampered = tmp_path / "tampered"
    shutil.copytree(base_dir, tampered)
    (tampered / "arial.ttf").write_bytes(b"TAMPERED")
    tampered_result = check_font_set(tampered)
    assert tampered_result["ok"] is False
    assert "arial.ttf" in tampered_result["hash_mismatches"]
    assert tampered_result["missing_fonts"] == []
    assert tampered_result["unregistered_fonts"] == []

    deleted = tmp_path / "deleted"
    shutil.copytree(base_dir, deleted)
    manifest = json.loads((deleted / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = [
        entry for entry in manifest["files"] if entry["name"] != "times.ttf"
    ]
    (deleted / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    deleted_result = check_font_set(deleted)
    assert deleted_result["ok"] is False
    assert "times.ttf" in deleted_result["unregistered_fonts"]
    assert deleted_result["hash_mismatches"] == []
    assert deleted_result["missing_fonts"] == []

    extra = tmp_path / "extra"
    shutil.copytree(base_dir, extra)
    _write_font(extra, "verdana.ttf")
    extra_result = check_font_set(extra)
    assert extra_result["ok"] is False
    assert "verdana.ttf" in extra_result["unregistered_fonts"]
    assert extra_result["hash_mismatches"] == []
    assert extra_result["missing_fonts"] == []

    missing = tmp_path / "missing"
    shutil.copytree(base_dir, missing)
    (missing / "times.ttf").unlink()
    missing_result = check_font_set(missing)
    assert missing_result["ok"] is False
    assert "times.ttf" in missing_result["missing_fonts"]
    assert missing_result["hash_mismatches"] == []
    assert missing_result["unregistered_fonts"] == []
    assert all(
        result["problems"]
        for result in (tampered_result, deleted_result, extra_result, missing_result)
    )


def test_detection_fonts_lists_and_matching(tmp_path: Path) -> None:
    assert set(DETECTION_FONTS) == {"windows", "office", "macos"}
    assert len(DETECTION_FONTS["windows"]) == 8
    assert len(DETECTION_FONTS["office"]) == 10
    assert len(DETECTION_FONTS["macos"]) == 20
    for names in DETECTION_FONTS.values():
        for name in names:
            assert "/" not in name
            assert "\\" not in name
            assert os.path.basename(name) == name
            assert Path(name).suffix.lower() in FONT_EXTENSIONS

    source = _make_source(tmp_path / "src", ["arial.ttf", "calibri.ttf", "PingFang.ttc"])
    root = tmp_path / "fonts"
    result = _import_fonts(root, [source])
    detection = check_font_set(result["dir"])["detection"]
    assert set(detection) == {"windows", "office", "macos"}
    assert detection["windows"]["total"] == 8
    assert detection["windows"]["matched"] == 2
    assert "arial.ttf" not in detection["windows"]["missing"]
    assert "calibri.ttf" not in detection["windows"]["missing"]
    assert detection["office"]["total"] == 10
    assert "calibri.ttf" not in detection["office"]["missing"]
    assert detection["office"]["matched"] >= 1
    assert detection["macos"]["total"] == 20
    assert "PingFang.ttc" not in detection["macos"]["missing"]
    assert detection["macos"]["matched"] >= 1
    assert len(detection["windows"]["missing"]) == 6


def test_list_font_sets_sorted_and_default(tmp_path: Path, monkeypatch) -> None:
    source = _make_source(tmp_path / "src", ["arial.ttf"])
    root = tmp_path / "fonts"
    old = _import_fonts(
        root, [source], created_at="2026-01-01T00:00:00+00:00"
    )
    _write_font(source, "times.ttf")
    new = _import_fonts(
        root, [source], created_at="2026-07-01T00:00:00+00:00"
    )
    macos = _import_fonts(
        root,
        [source],
        platform="macos",
        created_at="2026-09-01T00:00:00+00:00",
    )

    items = list_font_sets(root)
    keys = [(item["platform"], item["set_id"]) for item in items]
    assert keys == sorted(keys)
    assert len(items) == 3
    assert {
        "platform",
        "set_id",
        "source",
        "source_version",
        "created_at",
        "integrity",
        "file_count",
    } <= set(items[0])
    assert all(item["integrity"]["ok"] for item in items)
    assert default_font_set("windows", root) == new["set_id"]
    assert default_font_set("windows", root) != old["set_id"]
    assert default_font_set("macos", root) == macos["set_id"]
    assert default_font_set("linux", root) is None
    assert default_font_set("windows", tmp_path / "absent") is None
    assert list_font_sets(tmp_path / "absent") == []

    monkeypatch.delenv("CBROWSER_FONTS_DIR", raising=False)
    assert list_font_sets() == []
    assert default_font_set("windows") is None


def test_get_font_set_validation(tmp_path: Path, monkeypatch) -> None:
    source = _make_source(tmp_path / "src", ["arial.ttf"])
    root = tmp_path / "fonts"
    result = _import_fonts(root, [source])
    set_id = result["set_id"]

    found = get_font_set("windows", set_id, root)
    assert found is not None
    path, manifest = found
    assert path == Path(result["dir"])
    assert manifest["platform"] == "windows"
    assert manifest["files"][0]["name"] == "arial.ttf"

    assert get_font_set("macos", set_id, root) is None
    assert get_font_set("linux", set_id, root) is None
    assert get_font_set("windows", "0" * 64, root) is None
    assert get_font_set("windows", "../evil", root) is None
    assert get_font_set("windows", set_id.upper(), root) is None
    assert get_font_set("windows", set_id[:16], root) is None
    assert get_font_set("windows", set_id + "0", root) is None
    assert get_font_set("windows", set_id, tmp_path / "absent") is None

    monkeypatch.delenv("CBROWSER_FONTS_DIR", raising=False)
    assert get_font_set("windows", set_id) is None


def test_discover_merges_multiple_sources(tmp_path: Path) -> None:
    first = _make_source(tmp_path / "a", ["arial.ttf", "times.ttf"])
    second = _make_source(tmp_path / "b", ["verdana.ttf"])
    _write_font(second, "arial.ttf", _font_bytes("arial.ttf"))

    entries = discover_font_files([first, second])
    assert [entry[0] for entry in entries] == ["arial.ttf", "times.ttf", "verdana.ttf"]
    assert all(Path(entry[1]).is_absolute() for entry in entries)
    assert all(len(entry[2]) == 64 for entry in entries)

    root = tmp_path / "fonts"
    result = _import_fonts(root, [first, second])
    manifest = json.loads(
        (Path(result["dir"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert [entry["name"] for entry in manifest["files"]] == [
        "arial.ttf",
        "times.ttf",
        "verdana.ttf",
    ]
    assert result["file_count"] == 3

    _write_font(second, "arial.ttf", b"CONFLICT")
    with pytest.raises(ValueError):
        discover_font_files([first, second])


def test_cli_help() -> None:
    completed = subprocess.run(
        [sys.executable, str(CLI), "--help"],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    for flag in ("--platform", "--source", "--source-version", "--fonts-dir"):
        assert flag in completed.stdout


def test_cli_real_import(tmp_path: Path) -> None:
    source = _make_source(tmp_path / "src", ["arial.ttf", "calibri.ttf"])
    root = tmp_path / "fonts"
    completed = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--platform",
            "windows",
            "--source",
            str(source),
            "--source-version",
            "win11-26H2",
            "--fonts-dir",
            str(root),
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip())
    assert payload["created"] is True
    assert payload["platform"] == "windows"
    manifest_path = root / "windows" / payload["set_id"] / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_version"] == "win11-26H2"
    assert [entry["name"] for entry in manifest["files"]] == [
        "arial.ttf",
        "calibri.ttf",
    ]


def test_cli_fails_without_root(tmp_path: Path) -> None:
    source = _make_source(tmp_path / "src", ["arial.ttf"])
    environment = dict(os.environ)
    environment.pop("CBROWSER_FONTS_DIR", None)
    completed = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--platform",
            "windows",
            "--source",
            str(source),
            "--source-version",
            "win11-26H2",
        ],
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode != 0
