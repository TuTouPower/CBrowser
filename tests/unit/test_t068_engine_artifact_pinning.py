"""t068 AC-003: engine artifact pinning, integrity verification & auto-update lock."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cbrowser.supervisor.container_spec import cache_init_environment
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator

ROOT = Path(__file__).resolve().parents[2]


def _make_fake_elf_binary(path: Path, elf_machine: int, payload: bytes = b"") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    header[18:20] = elf_machine.to_bytes(2, "little")
    data = bytes(header) + payload
    path.write_bytes(data)
    path.chmod(0o755)
    return hashlib.sha256(data).hexdigest()


def test_approved_registry_pins_adr021_wrapper_and_arm64_artifact() -> None:
    from cbrowser.engine_artifacts import (
        CLOAKBROWSER_PACKAGE_VERSION,
        get_approved_artifact,
        verify_wrapper_package,
    )

    assert CLOAKBROWSER_PACKAGE_VERSION == "0.6.4"
    wrapper = verify_wrapper_package()
    assert wrapper["version"] == "0.6.4"
    arm64 = get_approved_artifact("linux-arm64")
    assert arm64.engine_build == "146.0.7680.177.3"
    assert arm64.chromium_version == "146.0.7680.177"
    assert arm64.binary_sha256 == (
        "3cf5231598c4fd44be1ed10c58cab4a1d59cd18b05a4800c73b946e0bfc4d34f"
    )
    assert arm64.archive_sha256 == (
        "8b71ce53b4fd131327331a31fba3835d71882d19bfaabde78dd0f5390bd16f45"
    )
    assert "Ed25519" in arm64.trust_source


def test_unapproved_engine_build_rejected() -> None:
    from cbrowser.engine_artifacts import EngineArtifactError, get_approved_artifact

    with pytest.raises(EngineArtifactError) as exc_info:
        get_approved_artifact("linux-arm64", "155.0.0.1")
    assert exc_info.value.code == "unapproved_engine_build"


def test_verify_extracted_cache_passes_valid_and_rejects_corruption(
    tmp_path: Path,
) -> None:
    from cbrowser.engine_artifacts import (
        ApprovedEngineArtifact,
        EngineArtifactError,
        verify_extracted_engine_cache,
    )

    cache = tmp_path / "engine-cache"
    build_dir = cache / "chromium-146.0.7680.177.3"
    chrome = build_dir / "chrome"
    lib = build_dir / "libGLESv2.so"
    chrome_sha = _make_fake_elf_binary(chrome, 183, b"good-chrome")
    lib.write_bytes(b"good-lib")
    lib_sha = hashlib.sha256(b"good-lib").hexdigest()

    registry = {
        ("linux-arm64", "146.0.7680.177.3"): ApprovedEngineArtifact(
            platform_tag="linux-arm64",
            engine_build="146.0.7680.177.3",
            chromium_version="146.0.7680.177",
            elf_machine=183,
            archive_name="cloakbrowser-linux-arm64.tar.gz",
            archive_sha256="a" * 64,
            binary_sha256=chrome_sha,
            file_sha256s={"chrome": chrome_sha, "libGLESv2.so": lib_sha},
            integrity_mechanism="test",
            trust_source="test",
            signing_pubkeys=("pub",),
        )
    }

    res = verify_extracted_engine_cache(
        cache,
        platform_tag="linux-arm64",
        engine_build="146.0.7680.177.3",
        run_version_probe=False,
        registry=registry,
    )
    assert res.binary_sha256 == chrome_sha
    assert res.verified_files_count == 2

    # Tamper supporting shared library -> fail closed
    lib.write_bytes(b"corrupted-lib")
    with pytest.raises(EngineArtifactError) as exc_lib:
        verify_extracted_engine_cache(
            cache,
            platform_tag="linux-arm64",
            engine_build="146.0.7680.177.3",
            run_version_probe=False,
            registry=registry,
        )
    assert exc_lib.value.code == "corrupted_engine_file"

    # Restore lib, tamper chrome binary -> fail closed
    lib.write_bytes(b"good-lib")
    chrome.write_bytes(b"tampered-not-elf")
    with pytest.raises(EngineArtifactError) as exc_bin:
        verify_extracted_engine_cache(
            cache,
            platform_tag="linux-arm64",
            engine_build="146.0.7680.177.3",
            run_version_probe=False,
            registry=registry,
        )
    assert exc_bin.value.code in {"elf_architecture_mismatch", "corrupted_engine_binary"}

    # Restore valid ELF chrome + lib, verify --version probe mismatch fails closed
    _make_fake_elf_binary(chrome, 183, b"good-chrome")
    chrome.chmod(0o755)
    orig_run = subprocess.run

    def _fake_version_probe(cmd, *args, **kwargs):
        if len(cmd) >= 2 and cmd[1] == "--version":
            return subprocess.CompletedProcess(cmd, 0, stdout="Chromium 145.0.0.0\n", stderr="")
        return orig_run(cmd, *args, **kwargs)

    import cbrowser.engine_artifacts as ea

    orig_ea_run = ea.subprocess.run
    ea.subprocess.run = _fake_version_probe
    try:
        with pytest.raises(EngineArtifactError) as exc_ver:
            verify_extracted_engine_cache(
                cache,
                platform_tag="linux-arm64",
                engine_build="146.0.7680.177.3",
                run_version_probe=True,
                registry=registry,
            )
        assert exc_ver.value.code == "version_probe_mismatch"
    finally:
        ea.subprocess.run = orig_ea_run


def test_auto_update_markers_and_bypass_envs_are_rejected(tmp_path: Path) -> None:
    from cbrowser.engine_artifacts import (
        EngineArtifactError,
        check_forbidden_engine_env,
        verify_extracted_engine_cache,
    )

    problems = check_forbidden_engine_env(
        {
            "CLOAKBROWSER_AUTO_UPDATE": "true",
            "CLOAKBROWSER_DOWNLOAD_URL": "https://evil.example",
            "CLOAKBROWSER_SKIP_CHECKSUM": "true",
            "CLOAKBROWSER_LICENSE_KEY": "free-key",
            "CLOAKBROWSER_VERSION": "155.0.0.1",
        },
        expected_build="146.0.7680.177.3",
    )
    assert len(problems) == 5

    cache = tmp_path / "engine-cache"
    cache.mkdir(parents=True)
    (cache / "latest_version_linux-arm64").write_text("199.0.0.0.1")
    with pytest.raises(EngineArtifactError) as exc_info:
        verify_extracted_engine_cache(
            cache,
            platform_tag="linux-arm64",
            engine_build="146.0.7680.177.3",
            run_version_probe=False,
        )
    assert exc_info.value.code == "auto_update_marker_present"


def test_cache_init_environment_disables_auto_update_and_pins_version() -> None:
    env = cache_init_environment(True, "marker.json", "run1", engine_build="146.0.7680.177.3")
    assert env["CLOAKBROWSER_AUTO_UPDATE"] == "false"
    assert env["CLOAKBROWSER_VERSION"] == "146.0.7680.177.3"
    assert env["CBROWSER_ENGINE_BUILD"] == "146.0.7680.177.3"
    assert env["CLOAKBROWSER_CACHE_DIR"] == "/data/engine-cache"
    assert env["CBROWSER_INIT_GEOIP"] == "1"


def test_docker_adapter_cache_init_rejects_corrupted_binary_in_script(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    (engine / "geoip").mkdir(parents=True)
    captured: dict[str, object] = {}

    class _Container:
        def wait(self, timeout=600):
            return {"StatusCode": 0}

        def remove(self, force=True):
            return None

    def fake_run(*args, **kwargs):
        captured["command"] = kwargs.get("command")
        captured["environment"] = kwargs.get("environment")
        return _Container()

    client = SimpleNamespace(containers=SimpleNamespace(run=fake_run))
    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=client,
        browser_image="sha256:" + "a" * 64,
        stream_image="sha256:" + "b" * 64,
        engine_build="146.0.7680.177.3",
    )
    # Without marker written by the fake container, ensure fails closed
    with pytest.raises(Exception):
        adapter._initialize_cache(False)

    script = captured["command"][1]
    assert "verify_extracted_engine_cache" in script
    assert "enforce_pinned_engine_env" in script
    assert captured["environment"]["CLOAKBROWSER_AUTO_UPDATE"] == "false"
    assert captured["environment"]["CBROWSER_ENGINE_BUILD"] == "146.0.7680.177.3"

    # Actually execute the captured script with a corrupted binary to prove it fails closed
    corrupt_dir = tmp_path / "corrupt_exec_cache" / "chromium-146.0.7680.177.3"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "chrome").write_bytes(b"NOT_AN_ELF")
    (corrupt_dir / "chrome").chmod(0o755)
    patched_script = script.replace(
        "Path('/data/engine-cache')",
        f"Path({str(tmp_path / 'corrupt_exec_cache')!r})",
    )
    proc = subprocess.run(
        [sys.executable, "-c", patched_script],
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "src" / "backend"),
            "CLOAKBROWSER_CACHE_DIR": str(tmp_path / "corrupt_exec_cache"),
            "CLOAKBROWSER_AUTO_UPDATE": "false",
            "CLOAKBROWSER_VERSION": "146.0.7680.177.3",
            "CBROWSER_ENGINE_BUILD": "146.0.7680.177.3",
            "CBROWSER_INIT_GEOIP": "0",
            "CBROWSER_INIT_MARKER": "m.json",
            "CBROWSER_INIT_RUN_ID": "r1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert not (tmp_path / "corrupt_exec_cache" / "m.json").exists()


def test_browser_runner_rejects_unverified_or_bypass_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cbrowser.runtime_agent.runner import BrowserRunner

    snap = tmp_path / "snapshot.json"
    snap.write_text(
        json.dumps(
            {
                "id": "s1",
                "profile_id": "p1",
                "version": 1,
                "config": {"name": "p1"},
                "created_at": "2026-11-13T00:00:00+08:00",
            }
        )
    )
    runner = BrowserRunner(
        "p1",
        "i1",
        snap,
        tmp_path / "run",
        tmp_path / "profile",
        engine_cache_dir=tmp_path / "engine_cache",
    )
    monkeypatch.setenv("CLOAKBROWSER_SKIP_CHECKSUM", "true")
    with pytest.raises(RuntimeError, match="bypass|forbidden"):
        runner.resolve_engine_binary()

    monkeypatch.delenv("CLOAKBROWSER_SKIP_CHECKSUM")
    # Corrupted cache directory or auto-update marker also fails resolve_engine_binary()
    bad_cache = tmp_path / "engine_cache" / "chromium-146.0.7680.177.3"
    bad_cache.mkdir(parents=True)
    (bad_cache / "chrome").write_bytes(b"not-elf")
    (bad_cache / "chrome").chmod(0o755)
    with pytest.raises(RuntimeError, match="verification failed|corrupt|missing|elf"):
        runner.resolve_engine_binary()
    (tmp_path / "engine_cache" / "latest_version_linux-arm64").write_text("199.0.0.1")
    with pytest.raises(RuntimeError, match="auto_update_marker_present"):
        runner.resolve_engine_binary()

    env = runner._browser_environment(
        tmp_path / "pulse.sock",
        tmp_path / "pulse.cookie",
        tmp_path / "chrome_wrapper.sh",
    )
    assert env["CLOAKBROWSER_AUTO_UPDATE"] == "false"


def test_deploy_refuses_corrupted_engine_cache_and_auto_update_bypass(
    tmp_path: Path,
) -> None:
    from tests.unit.test_t027_release_controller import (
        _deploy,
        _make_fake_bin,
        _make_fake_repo,
        _manifest,
    )

    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)

    # Bypass env var must fail closed before any build
    bad_env = _deploy(repo, bin_dir, "rel-bypass", CLOAKBROWSER_AUTO_UPDATE="true")
    assert bad_env.returncode != 0
    assert "CLOAKBROWSER_AUTO_UPDATE" in bad_env.stderr

    # Corrupted pre-populated engine cache must fail closed before compose up
    cache_dir = repo / "data" / "instance" / "engine-cache" / "chromium-146.0.7680.177.3"
    cache_dir.mkdir(parents=True)
    (cache_dir / "chrome").write_bytes(b"corrupted")
    (cache_dir / "chrome").chmod(0o755)
    bad_cache = _deploy(repo, bin_dir, "rel-corrupt")
    assert bad_cache.returncode != 0
    assert "corrupt" in bad_cache.stderr.lower() or "engine" in bad_cache.stderr.lower()

    # Clean empty engine-cache succeeds and records pinned engine block in manifest + env
    shutil.rmtree(repo / "data" / "instance" / "engine-cache")
    ok = _deploy(repo, bin_dir, "rel-ok")
    assert ok.returncode == 0, ok.stderr
    manifest = _manifest(repo, "rel-ok")
    assert manifest["engine"]["cloakbrowser_package"] == "0.6.4"
    assert manifest["engine"]["auto_update_disabled"] is True
    assert manifest["engine"]["engine_build"]
    env_text = (repo / "config" / "deploy" / "releases" / "rel-ok.env").read_text()
    assert "CLOAKBROWSER_AUTO_UPDATE=false" in env_text
    assert "CBROWSER_ENGINE_BUILD=" in env_text
