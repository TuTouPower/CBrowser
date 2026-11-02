"""HTTP integration for profile duplicate and reset."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.app import create_app
from cbrowser.domain.models import ProfileConfig
from fastapi.testclient import TestClient


@pytest.fixture
def profile_env(tmp_path: Path):
    db_file = tmp_path / "profiles.db"
    run_database_migrations(db_file)
    engine, maker = create_engine_and_maker(db_file)
    source_dir = tmp_path / "profiles" / "p1" / "profile"
    source_dir.mkdir(parents=True)
    (source_dir / "Cookies").write_bytes(b"source-cookie")
    (source_dir / "Default").mkdir()
    (source_dir / "Default" / "Preferences").write_text("{}", encoding="utf-8")
    (source_dir / "SingletonLock").symlink_to("host-1")

    import asyncio

    async def seed():
        await ProfileRepository(maker).create_profile(
            ProfileConfig(name="Source", fingerprint_seed=4242),
            profile_id="p1",
            user_data_dir=str(source_dir),
        )
        await engine.dispose()

    asyncio.run(seed())

    password = secrets.token_urlsafe(24)
    password_file = tmp_path / "admin.txt"
    password_file.write_text(password, encoding="utf-8")
    password_file.chmod(0o600)
    origin = "https://app.cbrowser.local"
    app = create_app(
        db_path=db_file,
        admin_password_file=password_file,
        allowed_origins=[origin],
    )
    with TestClient(app, base_url=origin) as client:
        login = client.post("/api/v1/auth/login", json={"password": password})
        assert login.status_code == 200
        headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": origin,
        }
        yield {
            "client": client,
            "headers": headers,
            "source_dir": source_dir,
            "tmp_path": tmp_path,
            "db_file": db_file,
        }


def test_config_only_duplicate_creates_new_profile_without_state(profile_env) -> None:
    env = profile_env
    response = env["client"].post(
        "/api/v1/profiles/p1/duplicate",
        json={"include_browser_state": False},
        headers=env["headers"],
    )
    assert response.status_code == 201, response.text
    clone = response.json()
    assert clone["id"] != "p1"
    assert clone["name"] == "Source (copy)"
    assert clone["fingerprint_seed"] == 4242
    assert not Path(clone["user_data_dir"]).exists()
    assert env["source_dir"].joinpath("Cookies").read_bytes() == b"source-cookie"


def test_state_duplicate_requires_stopped_and_copies_state(profile_env) -> None:
    env = profile_env
    response = env["client"].post(
        "/api/v1/profiles/p1/duplicate",
        json={"include_browser_state": True, "name": "State copy"},
        headers=env["headers"],
    )
    assert response.status_code == 201, response.text
    clone = response.json()
    clone_dir = Path(clone["user_data_dir"])
    assert clone["name"] == "State copy"
    assert clone_dir.joinpath("Cookies").read_bytes() == b"source-cookie"
    assert clone_dir.joinpath("Default", "Preferences").read_text() == "{}"
    assert not clone_dir.joinpath("SingletonLock").exists()
    assert env["source_dir"].joinpath("Cookies").read_bytes() == b"source-cookie"


def test_state_duplicate_rejects_running_source(profile_env) -> None:
    env = profile_env
    engine, maker = create_engine_and_maker(env["db_file"])

    import asyncio

    async def mark_running():
        await ProfileRepository(maker).set_desired_state("p1", "running")
        await engine.dispose()

    asyncio.run(mark_running())
    response = env["client"].post(
        "/api/v1/profiles/p1/duplicate",
        json={"include_browser_state": True},
        headers=env["headers"],
    )
    assert response.status_code == 409


def test_reset_requires_confirmation_and_rerolls_seed(profile_env) -> None:
    env = profile_env
    missing = env["client"].post(
        "/api/v1/profiles/p1/reset",
        json={"confirm": False},
        headers=env["headers"],
    )
    assert missing.status_code == 400

    response = env["client"].post(
        "/api/v1/profiles/p1/reset",
        json={"confirm": True},
        headers=env["headers"],
    )
    assert response.status_code == 200, response.text
    reset = response.json()
    assert reset["fingerprint_seed"] != 4242
    assert reset["name"] == "Source"
    assert list(env["source_dir"].iterdir()) == []


def test_duplicate_is_idempotent_with_idempotency_key(profile_env) -> None:
    env = profile_env
    headers = {**env["headers"], "Idempotency-Key": "duplicate-once"}
    first = env["client"].post(
        "/api/v1/profiles/p1/duplicate",
        json={"include_browser_state": False},
        headers=headers,
    )
    second = env["client"].post(
        "/api/v1/profiles/p1/duplicate",
        json={"include_browser_state": False},
        headers=headers,
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    listed = env["client"].get("/api/v1/profiles").json()
    assert len(listed) == 2


def test_duplicate_rejects_blank_name_without_poisoning_list(profile_env) -> None:
    env = profile_env
    response = env["client"].post(
        "/api/v1/profiles/p1/duplicate",
        json={"include_browser_state": False, "name": "   "},
        headers=env["headers"],
    )
    assert response.status_code == 400
    listed = env["client"].get("/api/v1/profiles")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
