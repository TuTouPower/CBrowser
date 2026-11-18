"""t080: deploy harness scenarios under the named-volume storage contract.

These replace the t027/t051/t054 scenarios removed from
tests/unit/test_t027_release_controller.py (see the NOTE there): the
rendered Caddyfile and the font sets now live in the fake Docker named
volumes (``<repo>/.fake-state/volumes/<prefix>-data`` /
``<prefix>-fonts``), and compose mounts named volumes instead of host
directories.  The behavioral assertions (rollback serves the target
port, sha mismatch refuses without touching the live Caddyfile or the
pointer, fingerprints hash the rendered product, fonts preflight warns
but never blocks) are unchanged.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.unit.test_t027_release_controller import (
    ROOT,
    _deploy,
    _make_fake_bin,
    _make_fake_repo,
    _manifest,
    _pointer,
    _run,
    _service_block,
    _valid_font_set,
)


def _volume_caddyfile(repo: Path) -> Path:
    return repo / ".fake-state" / "volumes" / "cbrowser-data" / "network" / "Caddyfile"


def test_rollback_restores_target_port_not_current_port(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001", CBROWSER_HTTPS_PORT="56661").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002", CBROWSER_HTTPS_PORT="56662").returncode == 0
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode == 0, result.stderr
    assert _pointer(repo, "current_release") == "rel-001"
    caddyfile = _volume_caddyfile(repo)
    first_line = caddyfile.read_text(encoding="utf-8").splitlines()[0]
    assert "https_port 56661" in first_line
    assert "56662" not in first_line
    rendered_sha = hashlib.sha256(caddyfile.read_bytes()).hexdigest()
    assert rendered_sha == _manifest(repo, "rel-001")["caddyfile_sha256"]


def test_rollback_refuses_on_caddyfile_sha_mismatch_without_touching_disk(
    tmp_path: Path,
) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001", CBROWSER_HTTPS_PORT="56661").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002", CBROWSER_HTTPS_PORT="56662").returncode == 0
    caddyfile = _volume_caddyfile(repo)
    before = caddyfile.read_bytes()
    assert b"https_port 56662" in before.splitlines()[0]
    manifest_path = repo / "config" / "deploy" / "releases" / "rel-001.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["caddyfile_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode != 0
    assert "caddyfile_sha256" in result.stderr
    assert caddyfile.read_bytes() == before
    assert _pointer(repo, "current_release") == "rel-002"


def test_caddy_fingerprints_recorded_and_change_sensitive(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0

    def _env(release_id: str) -> dict[str, str]:
        text = (repo / "config" / "deploy" / "releases" / f"{release_id}.env").read_text(
            encoding="utf-8"
        )
        return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)

    def _rendered_caddy_sha(env: dict[str, str]) -> str:
        caddyfile = (
            repo
            / ".fake-state"
            / "volumes"
            / env["CBROWSER_DATA_VOLUME"]
            / "network"
            / "Caddyfile"
        )
        return hashlib.sha256(caddyfile.read_bytes()).hexdigest()

    env1 = _env("rel-001")
    assert env1["CBROWSER_CADDYFILE_SHA256"] == _rendered_caddy_sha(env1)
    dist = repo / "src" / "frontend" / "dist"
    listing = "".join(
        f"{path.relative_to(dist)} {hashlib.sha256(path.read_bytes()).hexdigest()}\n"
        for path in sorted(dist.rglob("*"))
        if path.is_file()
    )
    expected_frontend = hashlib.sha256(listing.encode()).hexdigest()
    assert env1["CBROWSER_FRONTEND_SHA256"] == expected_frontend

    net_config = repo / "src" / "backend" / "cbrowser" / "network_config.py"
    net_config.write_text(
        net_config.read_text(encoding="utf-8") + "\n# drill change\n",
        encoding="utf-8",
    )
    fake_pythonpath = f"{repo / 'src' / 'backend'}:{ROOT / 'src' / 'backend'}"
    result = _deploy(repo, bin_dir, "rel-002", PYTHONPATH=fake_pythonpath)
    assert result.returncode == 0, result.stderr
    env2 = _env("rel-002")
    assert env2["CBROWSER_CADDYFILE_SHA256"] == env1["CBROWSER_CADDYFILE_SHA256"]
    assert env2["CBROWSER_CADDYFILE_SHA256"] == _rendered_caddy_sha(env2)
    assert env2["CBROWSER_FRONTEND_SHA256"] == env1["CBROWSER_FRONTEND_SHA256"]
    assert env2["CBROWSER_API_IMAGE"] == env1["CBROWSER_API_IMAGE"]

    result = _deploy(repo, bin_dir, "rel-003", CBROWSER_HTTPS_PORT="56662")
    assert result.returncode == 0, result.stderr
    env3 = _env("rel-003")
    assert env3["CBROWSER_CADDYFILE_SHA256"] != env1["CBROWSER_CADDYFILE_SHA256"]
    assert env3["CBROWSER_CADDYFILE_SHA256"] == _rendered_caddy_sha(env3)
    assert env3["CBROWSER_FRONTEND_SHA256"] == env1["CBROWSER_FRONTEND_SHA256"]
    assert env3["CBROWSER_API_IMAGE"] == env1["CBROWSER_API_IMAGE"]


def test_compose_yaml_volumes_and_labels_contract() -> None:
    """t051 labels/DB contract (unchanged) + t080 volume wiring."""
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "  db:\n    name: ${CBROWSER_PREFIX:-cbrowser}-db" in text
    assert "  data:\n    name: ${CBROWSER_PREFIX:-cbrowser}-data" in text
    assert "  fonts:\n    name: ${CBROWSER_PREFIX:-cbrowser}-fonts" in text
    assert "  runtime:\n    name: ${CBROWSER_PREFIX:-cbrowser}-runtime" in text
    assert "/data/cbrowser.db" not in text
    assert "/data/db/cbrowser.db" in text
    api_block = _service_block(text, "api")
    assert "db:/data/db" in api_block
    assert "CBROWSER_DB_PATH: /data/db/cbrowser.db" in api_block
    # Fonts are an independent named volume, mounted at /fonts:ro.
    assert "CBROWSER_DATA_ROOT}/fonts" not in text
    for service in ("api", "supervisor"):
        block = _service_block(text, service)
        assert "- fonts:/fonts:ro" in block
        assert "CBROWSER_FONTS_DIR: /fonts" in block
    for service in ("api", "gateway", "supervisor", "caddy"):
        block = _service_block(text, service)
        assert "com.cbrowser.instance-id: ${CBROWSER_INSTANCE_ID:?" in block, service
        assert (
            "com.cbrowser.media-subnet-pool: ${CBROWSER_MEDIA_SUBNET_POOL:?" in block
        ), service
    supervisor_block = _service_block(text, "supervisor")
    assert (
        "CBROWSER_INSTANCE_ID: ${CBROWSER_INSTANCE_ID:?run scripts/deploy.sh first}"
        in supervisor_block
    )
    assert (
        "CBROWSER_MEDIA_SUBNET_POOL: ${CBROWSER_MEDIA_SUBNET_POOL:?run scripts/deploy.sh first}"
        in supervisor_block
    )


def test_fonts_preflight_warns_and_continues(tmp_path: Path) -> None:
    """AC-009/AC-010: an empty fonts volume warns but never blocks."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode == 0, result.stderr
    assert "WARNING" in result.stdout
    # The pre-t080 host-directory message ("fonts directory ... does
    # not exist") does not apply to the volume scenario; the volume
    # exists but is empty, which reports the no-valid-set warning.
    assert "no valid font set found" in result.stdout


def test_fonts_preflight_ok_with_valid_set(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _valid_font_set(repo / ".fake-state" / "volumes" / "cbrowser-fonts")
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode == 0, result.stderr
    assert "font sets ok" in result.stdout
    assert "windows/set-1" in result.stdout


def test_deploy_refuses_corrupted_engine_cache_in_volume(tmp_path: Path) -> None:
    """t068 scenario under t080 storage: the corrupted cache is seeded
    into the data volume; the auto-update bypass refusal is unchanged."""
    import shutil

    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)

    bad_env = _deploy(repo, bin_dir, "rel-bypass", CLOAKBROWSER_AUTO_UPDATE="true")
    assert bad_env.returncode != 0
    assert "CLOAKBROWSER_AUTO_UPDATE" in bad_env.stderr

    cache_dir = (
        repo
        / ".fake-state"
        / "volumes"
        / "cbrowser-data"
        / "engine-cache"
        / "chromium-146.0.7680.177.3"
    )
    cache_dir.mkdir(parents=True)
    (cache_dir / "chrome").write_bytes(b"corrupted")
    (cache_dir / "chrome").chmod(0o755)
    bad_cache = _deploy(repo, bin_dir, "rel-corrupt")
    assert bad_cache.returncode != 0
    assert "corrupt" in bad_cache.stderr.lower() or "engine" in bad_cache.stderr.lower()

    shutil.rmtree(cache_dir.parent)
    ok = _deploy(repo, bin_dir, "rel-ok")
    assert ok.returncode == 0, ok.stderr
    manifest = _manifest(repo, "rel-ok")
    assert manifest["engine"]["cloakbrowser_package"] == "0.6.4"
    assert manifest["engine"]["auto_update_disabled"] is True
    assert manifest["engine"]["engine_build"]
    env_text = (repo / "config" / "deploy" / "releases" / "rel-ok.env").read_text()
    assert "CLOAKBROWSER_AUTO_UPDATE=false" in env_text
    assert "CBROWSER_ENGINE_BUILD=" in env_text
