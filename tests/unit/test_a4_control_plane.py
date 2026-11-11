"""A4: control-plane automation throttling keys on the trusted-proxy client IP."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.v1.control_router import require_automation_token
from cbrowser.shared.client_ip import parse_trusted_proxy_cidrs
from cbrowser.auth.rate_limiter import LoginRateLimiter
from cbrowser.auth.service import AuthService
from fastapi import HTTPException
from starlette.requests import Request


@pytest_asyncio.fixture
async def control_ctx(tmp_path):
    db_path = tmp_path / "a4_control.db"
    run_database_migrations(db_path)
    engine, session_maker = create_engine_and_maker(db_path)
    service = AuthService(session_maker)
    app = SimpleNamespace(state=SimpleNamespace(trusted_proxy_cidrs=[]))
    yield service, app
    await engine.dispose()


def _request(app, peer, xff=None):
    headers = [(b"authorization", b"Bearer cbat_bad")]
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": (peer, 40000),
        "server": ("test", 80),
        "app": app,
    }
    return Request(scope)


async def _deny(service, app, peer, xff, profile_id):
    try:
        await require_automation_token(_request(app, peer, xff), profile_id, service)
    except HTTPException:
        return None
    raise AssertionError("expected 401 for a bad automation token")


def _spy(service):
    seen = []
    original = service.authorize_automation

    async def spy(token, profile_id, client_ip="unknown"):
        seen.append(client_ip)
        return await original(token, profile_id, client_ip=client_ip)

    service.authorize_automation = spy
    return seen


async def test_control_plane_resolves_xff_from_trusted_proxy(control_ctx):
    service, app = control_ctx
    app.state.trusted_proxy_cidrs = parse_trusted_proxy_cidrs("10.0.0.0/8")
    seen = _spy(service)
    await _deny(service, app, "10.0.0.1", "203.0.113.10, 10.0.0.7", "p1")
    assert seen == ["203.0.113.10"]


async def test_control_plane_source_only_buckets_isolate_two_sources(control_ctx):
    service, app = control_ctx
    app.state.trusted_proxy_cidrs = parse_trusted_proxy_cidrs("10.0.0.0/8")
    limiter = service._automation_limiter
    for _ in range(limiter.max_failures):
        await _deny(service, app, "10.0.0.1", "203.0.113.10", "p1")
    assert limiter.rate_limit_layer("203.0.113.10") == "source"
    assert limiter.rate_limit_layer("203.0.113.11") is None
    assert limiter.rate_limit_layer("10.0.0.1") is None


async def test_wrong_token_does_not_treat_whole_proxy_as_one_source(control_ctx):
    service, app = control_ctx
    app.state.trusted_proxy_cidrs = parse_trusted_proxy_cidrs("10.0.0.0/8")
    limiter = service._automation_limiter
    for _ in range(limiter.max_failures):
        await _deny(service, app, "10.0.0.5", "203.0.113.20", "p1")
    seen = _spy(service)
    await _deny(service, app, "10.0.0.5", "203.0.113.21", "p2")
    assert seen == ["203.0.113.21"]
    allowed, reason = await service.authorize_automation(
        "cbat_bad", "p2", client_ip="203.0.113.22"
    )
    assert allowed is False
    assert reason == "token_not_found"
    assert limiter.rate_limit_layer("203.0.113.20") == "source"


async def test_control_plane_bucket_is_source_only_across_profiles(control_ctx):
    service, app = control_ctx
    app.state.trusted_proxy_cidrs = parse_trusted_proxy_cidrs("10.0.0.0/8")
    limiter = service._automation_limiter
    for _ in range(limiter.max_failures):
        await _deny(service, app, "10.0.0.1", "203.0.113.30", "p1")
    allowed, reason = await service.authorize_automation(
        "cbat_bad", "p2", client_ip="203.0.113.30"
    )
    assert allowed is False
    assert reason == "rate_limited"


@pytest.mark.parametrize("trusted", [None, "198.51.100.0/24"])
async def test_control_plane_untrusted_peer_ignores_spoofed_xff(control_ctx, trusted):
    service, app = control_ctx
    app.state.trusted_proxy_cidrs = parse_trusted_proxy_cidrs(trusted)
    seen = _spy(service)
    await _deny(service, app, "10.0.0.1", "203.0.113.77", "p1")
    assert seen == ["10.0.0.1"]


async def test_control_plane_global_guessing_budget_is_preserved(control_ctx):
    service, _app = control_ctx
    limiter = service._automation_limiter
    assert limiter.global_max_failures == 200
    assert limiter.global_window_seconds == 15 * 60.0


def test_login_rate_limiter_keeps_independent_global_budget():
    limiter = LoginRateLimiter(
        max_failures=2,
        window_seconds=60.0,
        global_max_failures=3,
        global_window_seconds=900.0,
        clock=lambda: 1000.0,
    )
    limiter.record_failure("a")
    limiter.record_failure("a")
    assert limiter.rate_limit_layer("a") == "source"
    assert limiter.rate_limit_layer("b") is None
    limiter.record_failure("b")
    limiter.record_failure("c")
    assert limiter.rate_limit_layer("c") == "global"
