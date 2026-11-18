"""t080: deploy.sh / compose.yaml wiring for Linux-native volumes (ADR 029).

Source-level wiring contract in the same style as the other deploy.sh
source tests: formal runtime storage is the per-prefix named volumes,
release records carry volume identities, env-backup / env-restore mount
the data volume (never a host data root), and the Caddyfile fingerprint
is the render output's hash of the rendered product.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "deploy.sh"
COMPOSE = ROOT / "compose.yaml"


def _deploy_text() -> str:
    return DEPLOY.read_text(encoding="utf-8")


def _compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


def test_compose_declares_named_volumes_with_prefix_names() -> None:
    text = _compose_text()
    for kind in ("db", "data", "fonts", "runtime"):
        assert f"name: ${{CBROWSER_PREFIX:-cbrowser}}-{kind}" in text


def test_compose_services_mount_volumes_not_host_data_dirs() -> None:
    text = _compose_text()
    assert "- data:/data" in text
    assert "- fonts:/fonts:ro" in text
    assert "- data:${CBROWSER_DATA_ROOT:?set CBROWSER_DATA_ROOT}" in text
    assert "subpath: gates" in text
    assert "subpath: sockets" in text
    assert "subpath: network" in text
    # No host data/fonts directory is bind-mounted for runtime data.
    assert "${CBROWSER_DATA_ROOT:?set CBROWSER_DATA_ROOT}:/data" not in text
    assert "${CBROWSER_FONTS_DIR:?set CBROWSER_FONTS_DIR}:/fonts:ro" not in text
    assert "/network/Caddyfile:/etc/caddy/Caddyfile" not in text


def test_deploy_records_volume_identities_in_release_env_and_manifest() -> None:
    text = _deploy_text()
    assert "CBROWSER_DATA_VOLUME=$(data_volume_name)" in text
    assert "CBROWSER_FONTS_VOLUME=$(fonts_volume_name)" in text
    assert "CBROWSER_RUNTIME_VOLUME=$(runtime_volume_name)" in text
    assert '"storage_volumes"' in text


def test_env_backup_and_restore_mount_the_data_volume() -> None:
    text = _deploy_text()
    backup_section = text.split("cmd_env_backup()")[1].split("cmd_env_restore()")[0]
    assert "restore_point.py create" in backup_section
    assert '-v "$(db_volume_name):/db"' in backup_section
    assert '-v "$(data_volume_name):/data"' in backup_section
    assert '-v "$DATA_ROOT:/data"' not in backup_section
    restore_section = text.split("cmd_env_restore()")[1].split("cmd_status()")[0]
    assert '-v "$(data_volume_name):/data"' in restore_section
    assert '-v "$DATA_ROOT:/data"' not in restore_section


def test_deploy_renders_caddyfile_and_hashes_the_product() -> None:
    # Carried verbatim from the removed t054 test, plus the t080
    # fingerprint source: the render output's CADDYFILE_SHA256.
    text = _deploy_text()
    assert "-m cbrowser.network_config_cli" in text
    assert "render --network-dir" in text
    assert 'eval "$(network_config render' in text
    assert "init --network-dir" not in text
    assert "read --network-dir" not in text
    assert 'sha256_of_file "$ROOT/src/backend/cbrowser/network_config.py"' not in text
    assert 'caddyfile_sha="${CADDYFILE_SHA256:' in text
    assert "copy_into_data_volume" in text


def test_deploy_checks_engine_cache_and_fonts_inside_volumes() -> None:
    text = _deploy_text()
    assert "check_engine_cache_in_volume" in text
    assert '-v "$(fonts_volume_name):/fonts:ro"' in text
    assert "init_storage_volumes" in text


def test_compose_api_mounts_runtime_volume_at_data_runtime() -> None:
    # t080 f001: the API's /data/runtime must be the runtime volume
    # itself, so Profile deletion removes the real runtime tree.  The
    # assertion is scoped to the api service block and matches the
    # whole line exactly (t080_test_f001: a substring match over the
    # whole file would not catch a wrong target or another service).
    from tests.unit.test_t027_release_controller import _service_block

    block = _service_block(_compose_text(), "api")
    lines = [line.strip() for line in block.splitlines()]
    assert "- runtime:/data/runtime" in lines


def test_init_storage_volumes_stamps_identity_and_covers_fonts() -> None:
    # t080 f003: init-layout receives the deployment prefix and the
    # fonts volume so every target volume carries its identity marker.
    text = _deploy_text()
    assert '--fonts-root /fonts-vol --prefix "$PREFIX"' in text
    assert '-v "$(fonts_volume_name):/fonts-vol"' in text
