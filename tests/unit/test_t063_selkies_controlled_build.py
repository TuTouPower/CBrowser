"""t063: the controlled Selkies build is reproducible and fully identified.

The server package is built from the pinned upstream wheel plus the
ordered patch series in ``config/selkies/patches/``; the committed
identity manifest must describe the build exactly, the build must be
byte-for-byte reproducible, fail closed on any drift, and stay traceable
to the same upstream artifact as the vendored web client.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from scripts import build_selkies_controlled as build_module
from scripts import vendor_selkies_web as vendor_module

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "config" / "selkies" / "selkies_controlled_build.json"
PATCHES_DIR = REPO_ROOT / "config" / "selkies" / "patches"
WEB_MANIFEST_PATH = REPO_ROOT / "config" / "selkies" / "selkies_web_sha256.txt"
UPSTREAM_WHEEL_CACHE = Path(
    os.environ.get(
        "CBROWSER_SELKIES_WHEEL_CACHE", str(REPO_ROOT / ".scratch" / "selkies_wheels")
    )
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _source_wheel() -> Path:
    wheel = UPSTREAM_WHEEL_CACHE / vendor_module.PINNED_WHEEL_FILENAME
    assert wheel.is_file(), f"local Selkies wheel cache missing: {wheel}"
    return wheel


def _build(tmp_path: Path, name: str = "out.whl") -> tuple[Path, dict]:
    out = tmp_path / name
    identity = build_module.build_controlled_wheel(
        _source_wheel(), PATCHES_DIR, _manifest(), out
    )
    return out, identity


def test_manifest_consistent_with_vendor_pin_lock_and_web_client() -> None:
    manifest = _manifest()
    upstream = manifest["upstream"]
    # One pinned artifact: build manifest, vendor pin and lockfile agree.
    assert upstream["wheel_sha256"] == vendor_module.PINNED_WHEEL_SHA256
    assert upstream["wheel_filename"] == vendor_module.PINNED_WHEEL_FILENAME
    assert upstream["version"] == vendor_module.PINNED_SELKIES_VERSION
    assert upstream["wheel_url"] == vendor_module.PINNED_WHEEL_URL
    lock_text = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    selkies_block = re.search(
        r'\[\[package\]\]\nname = "selkies"\nversion = "([^"]+)"', lock_text
    )
    assert selkies_block is not None
    assert selkies_block.group(1) == upstream["version"]
    assert upstream["wheel_sha256"] in lock_text
    # The web client manifest is the recorded sibling from the same wheel.
    web = manifest["web_client"]
    assert web["manifest"] == "config/selkies/selkies_web_sha256.txt"
    assert web["manifest_sha256"] == _sha256(WEB_MANIFEST_PATH.read_bytes())


def test_patch_hashes_match_committed_patch_files() -> None:
    manifest = _manifest()
    files = [entry["file"] for entry in manifest["patches"]]
    assert files == sorted(p.name for p in PATCHES_DIR.glob("*.patch"))
    for entry in manifest["patches"]:
        data = (PATCHES_DIR / entry["file"]).read_bytes()
        assert _sha256(data) == entry["sha256"], entry["file"]


def test_build_is_reproducible_and_matches_manifest(tmp_path: Path) -> None:
    first, identity_first = _build(tmp_path, "first.whl")
    second, identity_second = _build(tmp_path, "second.whl")
    assert first.read_bytes() == second.read_bytes()
    manifest = _manifest()
    assert identity_first["wheel_sha256"] == manifest["controlled"]["wheel_sha256"]
    assert identity_second["wheel_sha256"] == manifest["controlled"]["wheel_sha256"]
    assert identity_first["controlled_version"] == manifest["controlled"]["version"]
    assert identity_first["wheel_filename"] == manifest["controlled"]["wheel_filename"]


def test_built_wheel_differs_from_upstream_only_at_declared_surface(
    tmp_path: Path,
) -> None:
    built, _ = _build(tmp_path)
    with zipfile.ZipFile(_source_wheel()) as zin:
        upstream = {i.filename: zin.read(i.filename) for i in zin.infolist()}
    with zipfile.ZipFile(built) as zbuilt:
        controlled = {i.filename: zbuilt.read(i.filename) for i in zbuilt.infolist()}

    manifest = _manifest()
    version = manifest["upstream"]["version"]
    cversion = manifest["controlled"]["version"]
    up_di = f"selkies-{version}.dist-info"
    ct_di = f"selkies-{cversion}.dist-info"
    declared_targets = {entry["target"] for entry in manifest["patches"]}

    changed: set[str] = set()
    for name, data in upstream.items():
        renamed = ct_di + name[len(up_di) :] if name.startswith(up_di + "/") else name
        if name.endswith("/RECORD"):
            continue
        if controlled.get(renamed) != data:
            changed.add(name)
    assert changed == declared_targets | {f"{up_di}/METADATA"}
    added = set(controlled) - {
        (ct_di + n[len(up_di) :] if n.startswith(up_di + "/") else n) for n in upstream
    }
    assert added == {"selkies/cbrowser_build.json"}

    # The in-wheel build stamp carries the same identity as the manifest.
    stamp = json.loads(controlled["selkies/cbrowser_build.json"])
    assert stamp["upstream"]["wheel_sha256"] == manifest["upstream"]["wheel_sha256"]
    assert stamp["controlled_version"] == cversion
    assert [p["sha256"] for p in stamp["patches"]] == [
        e["sha256"] for e in manifest["patches"]
    ]
    metadata = controlled[f"{ct_di}/METADATA"].decode("utf-8")
    assert f"Version: {cversion}\n" in metadata
    # METADATA differs from upstream in exactly the Version line.
    upstream_metadata = upstream[f"{up_di}/METADATA"].decode("utf-8")
    assert [
        line
        for line in upstream_metadata.splitlines()
        if line not in metadata.splitlines()
    ] == [f"Version: {version}"]
    assert [
        line
        for line in metadata.splitlines()
        if line not in upstream_metadata.splitlines()
    ] == [f"Version: {cversion}"]

    # RECORD is self-consistent: every recorded hash/size matches content.
    import base64 as _base64

    record_text = controlled[f"{ct_di}/RECORD"].decode("utf-8")
    recorded: dict[str, str] = {}
    for line in record_text.strip().splitlines():
        path, _, rest = line.partition(",")
        recorded[path] = rest
    assert set(recorded) == set(controlled)
    for path, rest in recorded.items():
        if path == f"{ct_di}/RECORD":
            assert rest == ","
            continue
        digest_b64, _, size = rest.partition(",")
        expected = _base64.urlsafe_b64encode(
            hashlib.sha256(controlled[path]).digest()
        ).rstrip(b"=").decode("ascii")
        assert digest_b64 == f"sha256={expected}", path
        assert int(size) == len(controlled[path]), path

    # Both patched modules still compile.
    for target in declared_targets:
        compile(controlled[target], target, "exec")


def test_build_fails_closed_on_tampered_patch(tmp_path: Path) -> None:
    tampered_dir = tmp_path / "patches"
    shutil.copytree(PATCHES_DIR, tampered_dir)
    victim = tampered_dir / _manifest()["patches"][0]["file"]
    victim.write_bytes(victim.read_bytes() + b"\n")
    with pytest.raises(build_module.ControlledBuildError, match="SHA256 drift"):
        build_module.build_controlled_wheel(
            _source_wheel(), tampered_dir, _manifest(), tmp_path / "x.whl"
        )


def test_build_fails_closed_on_context_drift(tmp_path: Path) -> None:
    # Rewriting a patch context line (and fixing its manifest hash) must
    # still fail: the applier matches context exactly, with no fuzz.
    drifted_dir = tmp_path / "patches"
    shutil.copytree(PATCHES_DIR, drifted_dir)
    manifest = _manifest()
    entry = manifest["patches"][0]
    victim = drifted_dir / entry["file"]
    text = victim.read_text(encoding="utf-8")
    assert "import signal" in text
    victim.write_text(text.replace("import signal", "import signals"), encoding="utf-8")
    entry["sha256"] = _sha256(victim.read_bytes())
    with pytest.raises(build_module.ControlledBuildError, match="context mismatch"):
        build_module.build_controlled_wheel(
            _source_wheel(), drifted_dir, manifest, tmp_path / "x.whl"
        )


def test_build_fails_closed_on_wrong_upstream_wheel(tmp_path: Path) -> None:
    wrong = tmp_path / vendor_module.PINNED_WHEEL_FILENAME
    wrong.write_bytes(b"not the pinned wheel")
    with pytest.raises(build_module.ControlledBuildError, match="SHA256 mismatch"):
        build_module.build_controlled_wheel(
            wrong, PATCHES_DIR, _manifest(), tmp_path / "x.whl"
        )


def test_patch_with_lying_hunk_counts_is_rejected(tmp_path: Path) -> None:
    lying_dir = tmp_path / "patches"
    shutil.copytree(PATCHES_DIR, lying_dir)
    manifest = _manifest()
    entry = manifest["patches"][0]
    victim = lying_dir / entry["file"]
    text = victim.read_text(encoding="utf-8")
    header = next(line for line in text.splitlines() if line.startswith("@@ -"))
    forged = re.sub(r"@@ -\d+,\d+", "@@ -1,999", header, count=1)
    assert forged != header
    victim.write_text(text.replace(header, forged, 1), encoding="utf-8")
    entry["sha256"] = _sha256(victim.read_bytes())
    with pytest.raises(build_module.ControlledBuildError, match="declares"):
        build_module.build_controlled_wheel(
            _source_wheel(), lying_dir, manifest, tmp_path / "x.whl"
        )


def test_explicit_missing_source_wheel_is_an_error_not_a_fallback() -> None:
    with pytest.raises(build_module.ControlledBuildError, match="not found"):
        build_module._resolve_source_wheel(
            _manifest(), Path("/nonexistent/selkies-2.2.1-py3-none-any.whl"), False
        )


def test_update_manifest_fails_when_web_manifest_missing(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["web_client"]["manifest"] = "config/selkies/does_not_exist.txt"
    bogus = tmp_path / "manifest.json"
    bogus.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(
        build_module.ControlledBuildError, match="web client manifest not found"
    ):
        build_module.compute_manifest_fields(bogus, PATCHES_DIR)
