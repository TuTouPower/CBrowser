"""API storage root separation: DB lives in /data/db, shared artifacts and
previews live in CBROWSER_DATA_ROOT (/data), never inside the DB directory."""

from __future__ import annotations

import secrets
from pathlib import Path

from cbrowser.api.app import create_app, resolve_storage_paths
from cbrowser.api.v1.deps import get_profile_service
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def test_resolve_storage_paths_separates_default_container_db_from_data_root() -> None:
    db, data, artifacts = resolve_storage_paths(environ={})
    assert db == Path("/data/db/cbrowser.db").resolve()
    assert data == Path("/data").resolve()
    assert artifacts == Path("/data/artifacts").resolve()


def test_resolve_storage_paths_honors_explicit_data_root_and_env(tmp_path: Path) -> None:
    db_file = tmp_path / "db_vol" / "cbrowser.db"
    shared_dir = tmp_path / "shared_data"
    db, data, artifacts = resolve_storage_paths(
        environ={
            "CBROWSER_DB_PATH": str(db_file),
            "CBROWSER_DATA_ROOT": str(shared_dir),
        }
    )
    assert db == db_file.resolve()
    assert data == shared_dir.resolve()
    assert artifacts == (shared_dir / "artifacts").resolve()
    assert not data.is_relative_to(db.parent)


def test_resolve_storage_paths_isolated_test_db_without_data_root_falls_back_to_parent(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "test.db"
    db, data, artifacts = resolve_storage_paths(db_path=db_file, environ={})
    assert db == db_file.resolve()
    assert data == tmp_path.resolve()
    assert artifacts == (tmp_path / "artifacts").resolve()


def test_create_app_binds_preview_and_artifacts_to_data_root_not_db_parent(
    tmp_path: Path,
) -> None:
    db_dir = tmp_path / "db_volume"
    data_dir = tmp_path / "shared_data"
    db_dir.mkdir()
    data_dir.mkdir()
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(secrets.token_urlsafe(16), encoding="utf-8")
    admin_file.chmod(0o600)

    app = create_app(
        db_path=db_dir / "cbrowser.db",
        data_root=data_dir,
        admin_password_file=admin_file,
    )
    with TestClient(app, base_url="https://127.0.0.1:56661"):
        profile_service = app.dependency_overrides[get_profile_service]()
        artifact_service = app.state.artifact_service
        preview_dir = profile_service.get_preview_dir("prof-1")
        assert preview_dir is not None
        assert preview_dir.resolve().is_relative_to(data_dir.resolve())
        assert not preview_dir.resolve().is_relative_to(db_dir.resolve())
        assert artifact_service.store.root == (data_dir / "artifacts").resolve()
        assert not artifact_service.store.root.is_relative_to(db_dir.resolve())


def test_compose_and_e2e_topology_declare_api_data_root_distinct_from_db() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    api_block = compose[compose.index("\n  api:") : compose.index("\n  gateway:")]
    assert "CBROWSER_DB_PATH: /data/db/cbrowser.db" in api_block
    assert "CBROWSER_DATA_ROOT: /data" in api_block

    topology = (
        ROOT / "tests" / "fixtures" / "gateway_probe" / "topology.py"
    ).read_text(encoding="utf-8")
    assert '"CBROWSER_DATA_ROOT": "/data"' in topology
