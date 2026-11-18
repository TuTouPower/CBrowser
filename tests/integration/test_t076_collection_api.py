"""t076: HTTP layer for the collection endpoints (AC-001/AC-002/AC-004/
AC-006).

Real app + real SQLite DB via TestClient; repository-level semantics are
covered in tests/unit/test_t076_collection_queries.py.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.models import ProfileRuntimeModel
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.app import create_app
from cbrowser.domain.egress_observation import (
    OBSERVATION_TTL_SECONDS,
    EgressObservation,
)
from cbrowser.domain.models import ProfileConfig
from cbrowser.domain.proxy_endpoint import ProxyEndpoint
from fastapi.testclient import TestClient

NOW = datetime.now(timezone.utc)
ORIGIN = "https://127.0.0.1:56661"


@pytest.fixture
def api_env(tmp_path: Path):
    db_file = tmp_path / "t076_api.db"
    run_database_migrations(db_file)
    admin_pwd_file = tmp_path / "admin_pwd.txt"
    admin_pwd = secrets.token_urlsafe(32)
    admin_pwd_file.write_text(admin_pwd, encoding="utf-8")
    app = create_app(db_path=db_file, admin_password_file=admin_pwd_file)

    async def _seed() -> dict:
        engine, session_maker = create_engine_and_maker(db_file)
        repo = ProfileRepository(session_maker)
        proxy_a = await repo.create_proxy(
            {
                "name": "px-a",
                "scheme": "http",
                "host": "a.example.com",
                "port": 8080,
                "username": "user",
                "password": "s3cret-pw",
            }
        )
        proxy_b = await repo.create_proxy(
            {
                "name": "px-b",
                "scheme": "http",
                "host": "b.example.com",
                "port": 8080,
                "username": "user",
                "password": "s3cret-pw",
            }
        )
        # P-bound: bound to A (v1), current moved to B.
        p_bound = await repo.create_profile(
            ProfileConfig(name="env-bound", proxy_id=proxy_a.id)
        )
        await repo.bind_runtime_instance(
            p_bound.id, "inst-bound", config_version=1
        )
        await repo.update_profile(p_bound.id, {"proxy_id": proxy_b.id})
        p_plain = await repo.create_profile(
            ProfileConfig(name="env-plain", proxy_id=proxy_b.id)
        )
        await repo.record_egress_observation(
            proxy_a.id,
            EgressObservation(
                proxy_id=proxy_a.id,
                endpoint_fingerprint=ProxyEndpoint(
                    scheme="http", host="a.example.com", port=8080, username="user"
                ).fingerprint,
                credential_revision=proxy_a.credential_revision,
                status="ok",
                egress_ip="203.0.113.9",
                country_code="JP",
                city="Tokyo",
                observed_at=NOW,
                expires_at=NOW + timedelta(seconds=OBSERVATION_TTL_SECONDS),
            ),
        )
        await engine.dispose()
        return {
            "proxy_a": proxy_a.id,
            "proxy_b": proxy_b.id,
            "p_bound": p_bound.id,
            "p_plain": p_plain.id,
        }

    seeded = asyncio.run(_seed())
    with TestClient(app, base_url=ORIGIN) as client:
        login = client.post(
            "/api/v1/auth/login", json={"password": admin_pwd}
        )
        assert login.status_code == 200
        headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": ORIGIN,
        }
        yield {"client": client, "headers": headers, "db_file": db_file, **seeded}


def test_profiles_collection_search_and_page_size_clamp(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.get(
        "/api/v1/profiles/collection?search=env-bound",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert [i["name"] for i in body["items"]] == ["env-bound"]

    resp = client.get(
        "/api/v1/profiles/collection?page_size=500", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["page_size"] == 100
    assert resp.json()["total"] == 2


def test_profiles_collection_status_running_exact(api_env):
    """t076 review f008: the router accepts status=running_exact and
    it matches only observed running, while the running bucket still
    covers running + starting."""
    client, headers = api_env["client"], api_env["headers"]

    async def _flip() -> None:
        engine, session_maker = create_engine_and_maker(api_env["db_file"])
        try:
            async with session_maker() as session:
                rt = await session.get(
                    ProfileRuntimeModel, api_env["p_bound"]
                )
                rt.observed_state = "running"
                rt_plain = await session.get(
                    ProfileRuntimeModel, api_env["p_plain"]
                )
                rt_plain.observed_state = "starting"
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_flip())

    resp = client.get(
        "/api/v1/profiles/collection?status=running_exact", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert [i["name"] for i in body["items"]] == ["env-bound"]

    resp = client.get(
        "/api/v1/profiles/collection?status=running", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_proxy_used_by_endpoint_uses_union(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.get(
        f"/api/v1/proxies/{api_env['proxy_a']}/used-by", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["proxy_id"] == api_env["proxy_a"]
    assert [(e["profile_id"], e["kind"]) for e in body["entries"]] == [
        (api_env["p_bound"], "bound")
    ]

    resp = client.get(
        f"/api/v1/proxies/{api_env['proxy_b']}/used-by", headers=headers
    )
    assert resp.status_code == 200
    kinds = {
        e["profile_id"]: e["kind"] for e in resp.json()["entries"]
    }
    assert kinds == {
        api_env["p_bound"]: "current",
        api_env["p_plain"]: "both",
    }

    resp = client.get("/api/v1/proxies/no-such-proxy/used-by", headers=headers)
    assert resp.status_code == 404


def test_runtime_summary_single_payload(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.get("/api/v1/profiles/runtime-summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["running_count"] == 0
    by_id = {e["profile_id"]: e for e in body["entries"]}
    assert by_id[api_env["p_bound"]]["config_version"] == 1
    assert by_id[api_env["p_bound"]]["runtime_instance_id"] == "inst-bound"
    assert by_id[api_env["p_plain"]]["observed_state"] == "stopped"


def test_proxy_candidates_and_countries(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.get(
        "/api/v1/proxies/candidates?search=px-b", headers=headers
    )
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["px-b"]

    resp = client.get("/api/v1/proxies/countries", headers=headers)
    assert resp.status_code == 200
    by_code = {r["country_code"]: r for r in resp.json()}
    assert by_code["JP"]["cities"] == ["Tokyo"]


def test_groups_collection(api_env):
    client, headers = api_env["client"], api_env["headers"]
    resp = client.get("/api/v1/groups/collection", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []
