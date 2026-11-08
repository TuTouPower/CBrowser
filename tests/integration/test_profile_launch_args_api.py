"""launch_args write contract: create/update reject out-of-whitelist values.

AC-001 (A2): ProfileUpdateRequest keeps only the strict validator; the
PATCH tri-state for launch_args is absent=unchanged, null=clear,
list=replace, and any out-of-whitelist entry fails the whole request 422.
Historical rows keep being filtered on read by ProfileConfig.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.models import ProfileModel
from cbrowser.adapters.database.session import (
    create_engine_and_maker,
    write_transaction,
)
from cbrowser.api.app import create_app
from fastapi.testclient import TestClient

EVIL = "--load-extension=/tmp/evil"
GOOD = ["--mute-audio", "--lang=en-US"]


@pytest.fixture
def api_client(tmp_path: Path):
    db_file = tmp_path / "launch_args.db"
    run_database_migrations(db_file)
    admin_pass = secrets.token_urlsafe(32)
    admin_file = tmp_path / "admin.pwd"
    admin_file.write_text(admin_pass, encoding="utf-8")
    admin_file.chmod(0o600)
    app = create_app(
        db_path=db_file,
        admin_password_file=admin_file,
            )
    with TestClient(app, base_url="https://127.0.0.1:56661") as client:
        login = client.post("/api/v1/auth/login", json={"password": admin_pass})
        assert login.status_code == 200
        client.headers.update(
            {
                "X-CSRF-Token": login.json()["csrf_token"],
                "Origin": "https://127.0.0.1:56661",
            }
        )
        yield client, db_file


def _create(client: TestClient, launch_args=None) -> str:
    payload = {"name": "args_profile"}
    if launch_args is not None:
        payload["launch_args"] = launch_args
    response = client.post("/api/v1/profiles", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _args(client: TestClient, profile_id: str) -> list[str]:
    return client.get(f"/api/v1/profiles/{profile_id}").json()["launch_args"]


def test_create_rejects_out_of_whitelist_launch_args(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/v1/profiles", json={"name": "bad", "launch_args": [EVIL]}
    )
    assert response.status_code == 422
    assert client.get("/api/v1/profiles").json() == []


def test_create_accepts_whitelisted_launch_args(api_client) -> None:
    client, _ = api_client
    profile_id = _create(client, GOOD)
    assert _args(client, profile_id) == GOOD


@pytest.mark.parametrize("method", ["put", "patch"])
def test_update_rejects_out_of_whitelist_launch_args(api_client, method) -> None:
    client, _ = api_client
    profile_id = _create(client, GOOD)
    response = getattr(client, method)(
        f"/api/v1/profiles/{profile_id}", json={"launch_args": [EVIL]}
    )
    assert response.status_code == 422
    # Stored value is untouched by the rejected write.
    assert _args(client, profile_id) == GOOD


@pytest.mark.parametrize("method", ["put", "patch"])
def test_update_accepts_whitelisted_launch_args(api_client, method) -> None:
    client, _ = api_client
    profile_id = _create(client)
    response = getattr(client, method)(
        f"/api/v1/profiles/{profile_id}", json={"launch_args": GOOD}
    )
    assert response.status_code == 200
    assert response.json()["launch_args"] == GOOD
    assert _args(client, profile_id) == GOOD


def test_update_absent_launch_args_preserves_and_null_clears(api_client) -> None:
    client, _ = api_client
    profile_id = _create(client, GOOD)

    untouched = client.patch(
        f"/api/v1/profiles/{profile_id}", json={"notes": "no args field"}
    )
    assert untouched.status_code == 200
    assert _args(client, profile_id) == GOOD

    cleared = client.patch(
        f"/api/v1/profiles/{profile_id}", json={"launch_args": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["launch_args"] == []
    assert _args(client, profile_id) == []


@pytest.mark.asyncio
async def test_historical_row_launch_args_are_filtered_on_read(api_client) -> None:
    client, db_file = api_client
    profile_id = _create(client, GOOD)
    engine, session_maker = create_engine_and_maker(db_file)
    async with session_maker() as session, write_transaction(session):
        row = await session.get(ProfileModel, profile_id)
        row.launch_args = json.dumps([GOOD[0], EVIL])
    await engine.dispose()
    # ProfileConfig read filtering drops the legacy out-of-whitelist entry.
    assert _args(client, profile_id) == [GOOD[0]]
