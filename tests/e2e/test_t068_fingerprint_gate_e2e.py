"""t068 real Docker/Engine E2E: cache_init pinning, 4-context baseline, TLS JA3/JA4 & drift gate."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import docker
import pytest

from cbrowser.engine_artifacts import (
    EngineArtifactError,
    enforce_pinned_engine_env,
    verify_extracted_engine_cache,
)
from cbrowser.fingerprint_verification.comparator import compare_reports
from e2e_env import complete_font_set_dir, require_e2e_available, require_e2e_env
from e2e_volumes import init_prefix_volumes, remove_prefix_volumes, run_volume_json

pytestmark = [
    pytest.mark.serial,
    pytest.mark.e2e_images(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
    ),
]


_T068_CACHE_DRIVER = """
import asyncio
import json
import os
from pathlib import Path

import docker
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator


async def main() -> None:
    root = Path("/data")
    engine = root / "engine-cache"
    for marker in ("latest_version", "latest_version_linux-arm64", ".last_update_check"):
        (engine / marker).unlink(missing_ok=True)

    client = docker.from_env()
    try:
        adapter = DockerAdapter(
            PathValidator(root),
            engine,
            docker_client=client,
            resource_prefix=os.environ["CB_TEST_PREFIX"],
            browser_image=os.environ["CB_TEST_BROWSER_IMAGE"],
            stream_image=os.environ["CB_TEST_STREAM_IMAGE"],
            engine_build="146.0.7680.177.3",
        )
        # 1. Real cache_init helper runs the pinned verification script and completes.
        await adapter.ensure_runtime_cache(need_geoip=False)
        markers_after_ok = [
            (engine / ".last_update_check").exists(),
            (engine / "latest_version_linux-arm64").exists(),
        ]

        # 3b. Tamper a supporting shared library inside volume -> helper fails closed.
        lib_file = engine / "chromium-146.0.7680.177.3" / "libGLESv2.so"
        original_lib = lib_file.read_bytes()
        lib_file.write_bytes(b"corrupted-lib")
        adapter._binary_ready = False
        corrupted_err = None
        try:
            await adapter.ensure_runtime_cache(need_geoip=False)
        except DockerSandboxError as exc:
            corrupted_err = str(exc)
        assert corrupted_err is not None, "Expected DockerSandboxError on corrupted lib"

        # Restore lib and verify auto-update bypass env refuses before helper run.
        lib_file.write_bytes(original_lib)
        os.environ["CLOAKBROWSER_AUTO_UPDATE"] = "true"
        bypass_err = None
        try:
            await adapter.ensure_runtime_cache(need_geoip=False)
        except DockerSandboxError as exc:
            bypass_err = str(exc)
        finally:
            os.environ.pop("CLOAKBROWSER_AUTO_UPDATE", None)
        assert bypass_err is not None and (
            "pinning" in bypass_err or "CLOAKBROWSER_AUTO_UPDATE" in bypass_err
        ), bypass_err

        # 7. With no bypass, the restored tree passes cache_init again.
        adapter._binary_ready = False
        adapter._validate_cache_paths()
        await adapter.ensure_runtime_cache(need_geoip=False)
        print(
            "CBROWSER_E2E_RESULT="
            + json.dumps({"markers_after_ok": markers_after_ok, "restored": True})
        )
    finally:
        client.close()


asyncio.run(main())
"""


def _run_container_measure(
    *,
    image: str,
    engine_cache: Path,
    fonts_root: Path,
    work_dir: Path,
    profile_id: str,
    config_version: int,
    config_payload: dict,
    out_name: str,
    samples: int = 2,
    use_tls: bool = True,
) -> dict:
    cfg_path = work_dir / f"{out_name}_cfg.json"
    cfg_path.write_text(json.dumps(config_payload), encoding="utf-8")
    args = [
        "-u",
        "-m",
        "cbrowser.fingerprint_verification",
        "measure",
        "--profile-id",
        profile_id,
        "--config-version",
        str(config_version),
        "--config-json",
        f"/work/{cfg_path.name}",
        "--engine-cache",
        "/data/engine-cache",
        "--fonts-dir",
        "/fonts",
        "--samples",
        str(samples),
        "--display",
        ":171",
        "--out",
        f"/work/{out_name}.json",
    ]
    if not use_tls:
        args.append("--no-tls")
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--init",
            "--shm-size=1g",
            "-v",
            f"{engine_cache}:/data/engine-cache:ro",
            "-v",
            f"{fonts_root}:/fonts:ro",
            "-v",
            f"{work_dir}:/work:rw",
            "--entrypoint",
            "python3",
            image,
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    out_file = work_dir / f"{out_name}.json"
    assert proc.returncode == 0 and out_file.is_file(), (
        f"container measure failed rc={proc.returncode}\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    return json.loads(out_file.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_ac003_cache_init_and_runner_pinning_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
        paths=("CBROWSER_RUNTIME_ENGINE_CACHE", "CBROWSER_RUNTIME_GEOIP_CACHE"),
        docker=True,
    )
    browser_img = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_img = env["CBROWSER_STREAM_TEST_IMAGE"]
    supervisor_img = env["CBROWSER_SUPERVISOR_TEST_IMAGE"]
    engine_src = Path(env["CBROWSER_RUNTIME_ENGINE_CACHE"])
    geoip_src = Path(env["CBROWSER_RUNTIME_GEOIP_CACHE"])

    root = tmp_path / "data"
    engine = root / "engine_cache"
    shutil.copytree(engine_src, engine)
    shutil.copytree(geoip_src, engine / "geoip", dirs_exist_ok=True)
    for marker in ("latest_version", "latest_version_linux-arm64", ".last_update_check"):
        (engine / marker).unlink(missing_ok=True)

    client = docker.from_env()
    prefix = f"t068_cache_{uuid.uuid4().hex[:10]}"
    try:
        init_prefix_volumes(
            client,
            prefix,
            supervisor_img,
            roles=("data", "runtime", "fonts"),
            engine_cache_src=engine_src,
            geoip_cache_src=geoip_src,
        )
        # 1 + 3b + 6b + 7: Real cache_init helper inside Supervisor named-volume env.
        driver_res = run_volume_json(
            client,
            prefix,
            supervisor_img,
            _T068_CACHE_DRIVER,
            roles=("data", "runtime", "fonts"),
            mount_docker_sock=True,
            env={
                "CB_TEST_PREFIX": prefix,
                "CB_TEST_BROWSER_IMAGE": browser_img,
                "CB_TEST_STREAM_IMAGE": stream_img,
            },
        )
        assert driver_res == {"markers_after_ok": [False, False], "restored": True}

        # 2. Direct extracted-cache verification passes on the real pinned tree.
        ok = verify_extracted_engine_cache(engine, run_version_probe=False)
        assert ok.verified_files_count == 15
        assert ok.engine_build == "146.0.7680.177.3"

        # 3. Tamper a supporting shared library -> direct verify fails closed.
        lib_file = engine / "chromium-146.0.7680.177.3" / "libGLESv2.so"
        original_lib = lib_file.read_bytes()
        lib_file.write_bytes(b"corrupted-lib")
        with pytest.raises(EngineArtifactError) as exc_lib:
            verify_extracted_engine_cache(engine, run_version_probe=False)
        assert exc_lib.value.code == "corrupted_engine_file"

        # 4. Tamper the chrome binary -> fail closed.
        lib_file.write_bytes(original_lib)
        chrome_file = engine / "chromium-146.0.7680.177.3" / "chrome"
        original_chrome = chrome_file.read_bytes()
        chrome_file.write_bytes(b"#!/bin/sh\necho Chromium 146.0.7680.177\n")
        chrome_file.chmod(0o755)
        with pytest.raises(EngineArtifactError) as exc_bin:
            verify_extracted_engine_cache(engine, run_version_probe=False)
        assert exc_bin.value.code in {"elf_architecture_mismatch", "corrupted_engine_binary"}

        # 5. Restore, then an auto-update marker must be refused by verification.
        chrome_file.write_bytes(original_chrome)
        chrome_file.chmod(0o755)
        (engine / "latest_version_linux-arm64").write_text("199.0.0.0.1")
        with pytest.raises(EngineArtifactError) as exc_mark:
            verify_extracted_engine_cache(engine, run_version_probe=False)
        assert exc_mark.value.code == "auto_update_marker_present"
        (engine / "latest_version_linux-arm64").unlink(missing_ok=True)

        # 6. Bypass env vars are refused before any helper container can run.
        with pytest.raises(EngineArtifactError) as exc_env:
            enforce_pinned_engine_env(
                {
                    "CLOAKBROWSER_AUTO_UPDATE": "true",
                    "CLOAKBROWSER_SKIP_CHECKSUM": "true",
                    "CLOAKBROWSER_DOWNLOAD_URL": "https://evil.example",
                },
                expected_build="146.0.7680.177.3",
            )
        assert exc_env.value.code == "auto_update_bypass_env"
    finally:
        for container in client.containers.list(
            all=True, filters={"label": f"com.cbrowser.prefix={prefix}"}
        ):
            container.remove(force=True)
        remove_prefix_volumes(client, prefix)
        client.close()


def test_ac001_ac002_ac006_real_engine_gate_detects_controlled_timezone_drift(
    tmp_path: Path,
) -> None:
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_E2E_FONTS_DIR",
        paths=("CBROWSER_RUNTIME_ENGINE_CACHE", "CBROWSER_E2E_FONTS_DIR"),
        docker=True,
        fonts_platform="windows",
    )
    image = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    engine_cache = Path(env["CBROWSER_RUNTIME_ENGINE_CACHE"])
    fonts_root = Path(env["CBROWSER_E2E_FONTS_DIR"])
    win_set = complete_font_set_dir("windows", fonts_root)
    require_e2e_available(win_set is not None, "complete windows font set required")
    assert win_set is not None

    win_cfg = {
        "name": "e2e-win-fp",
        "fingerprint_seed": 290029,
        "fingerprint_platform": "windows",
        "font_set_id": win_set.name,
        "locale": "en-US",
        "timezone": "America/New_York",
        "screen_width": 1280,
        "screen_height": 800,
        "geoip": False,
        "humanize": False,
        "set_google_default": False,
        "restore_session": False,
    }

    baseline = _run_container_measure(
        image=image,
        engine_cache=engine_cache,
        fonts_root=fonts_root,
        work_dir=tmp_path,
        profile_id="prof-e2e-01",
        config_version=1,
        config_payload=win_cfg,
        out_name="baseline",
        samples=2,
        use_tls=True,
    )
    candidate_same = _run_container_measure(
        image=image,
        engine_cache=engine_cache,
        fonts_root=fonts_root,
        work_dir=tmp_path,
        profile_id="prof-e2e-01",
        config_version=1,
        config_payload=win_cfg,
        out_name="candidate_same",
        samples=2,
        use_tls=True,
    )

    # Full 4-context applicability matrix (AC-001/AC-002) & AC-006 consistency.
    assert baseline["consistency"]["verdict"] == "consistent"
    assert baseline["consistency"]["tls_status"] == "verified"
    assert baseline["tls_evidence"]["ja4_distribution"]["unique_values"]
    assert baseline["font_evidence"]["fc_list"]["linux_font_hits"] == 0
    for ctx in ("main", "iframe"):
        assert all(v == "ok" for v in baseline["context_matrix"][ctx].values()), ctx
    for ctx in ("worker", "service_worker"):
        assert baseline["context_matrix"][ctx]["audio"] == "unsupported_context"
        assert baseline["context_matrix"][ctx]["webrtc"] == "unsupported_context"
        assert baseline["context_matrix"][ctx]["canvas2d"] == "ok"
        assert baseline["context_matrix"][ctx]["webgl"] == "ok"
        assert baseline["context_matrix"][ctx]["uaDataHigh"] == "ok"
    # Worker/SW fetches do not carry Sec-CH-UA* headers (measured matrix).
    for req_cls in ("worker_fetch", "sw_fetch"):
        assert "sec-ch-ua-platform" not in baseline["http_headers"][req_cls], req_cls

    # Strict default gate blocks on unapproved raw JA3 BoringSSL shuffle;
    # explicit approved normalization lets the identical artifact pass.
    strict_diff = compare_reports(baseline, candidate_same)
    assert strict_diff["upgrade_decision"] == "blocked"
    assert "non_deterministic_variance:tls.ja3_raw" in strict_diff["blocking_reasons"]

    approved_diff = compare_reports(
        baseline,
        candidate_same,
        approved_rules={"tls_extension_shuffle_via_ja4": True},
    )
    assert approved_diff["upgrade_decision"] == "approved", approved_diff

    # Real HTTP-only probe -> TLS inconclusive -> blocks upgrade (AC-006).
    candidate_notls = _run_container_measure(
        image=image,
        engine_cache=engine_cache,
        fonts_root=fonts_root,
        work_dir=tmp_path,
        profile_id="prof-e2e-01",
        config_version=1,
        config_payload=win_cfg,
        out_name="candidate_notls",
        samples=1,
        use_tls=False,
    )
    assert candidate_notls["tls_evidence"]["status"] == "inconclusive"
    assert candidate_notls["consistency"]["verdict"] == "inconclusive"
    notls_diff = compare_reports(
        baseline,
        candidate_notls,
        approved_rules={"tls_extension_shuffle_via_ja4": True},
    )
    assert notls_diff["upgrade_decision"] == "blocked"
    assert "inconclusive:tls_capture" in notls_diff["blocking_reasons"]

    # Deliberately change the timezone input to validate drift detection
    # under the launch policy that disables seed-driven Canvas noise.
    drift_cfg = dict(win_cfg, timezone="Asia/Tokyo")
    candidate_drift = _run_container_measure(
        image=image,
        engine_cache=engine_cache,
        fonts_root=fonts_root,
        work_dir=tmp_path,
        profile_id="prof-e2e-01",
        config_version=1,
        config_payload=drift_cfg,
        out_name="candidate_drift",
        samples=1,
        use_tls=True,
    )
    drift_diff = compare_reports(
        baseline,
        candidate_drift,
        approved_rules={"tls_extension_shuffle_via_ja4": True},
    )
    assert drift_diff["upgrade_decision"] == "blocked"
    assert {
        (diff["context"], diff["baseline_value"], diff["candidate_value"])
        for diff in drift_diff["diffs"]
        if diff["classification"] == "unapproved_drift" and diff["field"] == "timezone"
    } == {
        (context, "America/New_York", "Asia/Tokyo")
        for context in ("main", "iframe", "worker", "service_worker")
    }
