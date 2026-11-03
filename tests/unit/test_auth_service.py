"""Unit tests for AuthService: admin, session, rate-limiting, and tokens."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.models import (
    AdminModel,
    AuditEventModel,
    ProfileModel,
    SessionModel,
)
from cbrowser.adapters.database.session import (
    create_engine_and_maker,
    write_transaction,
)
from cbrowser.auth.service import AuthService
from sqlalchemy import select


@pytest.fixture
async def auth_db(tmp_path: Path):
    db_file = tmp_path / "auth_service_test.db"
    run_database_migrations(db_file)
    engine, session_maker = create_engine_and_maker(db_file)
    service = AuthService(session_maker)
    yield service, session_maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_bootstrap_and_validation(auth_db, tmp_path: Path):
    service, session_maker = auth_db

    # 1. Missing file -> RuntimeError
    with pytest.raises(RuntimeError, match="not configured|does not exist"):
        await service.init_admin_password(tmp_path / "nonexistent.pwd")

    # 2. Too short password (< 12 bytes) -> RuntimeError
    short_file = tmp_path / "short.pwd"
    short_file.write_text("short123", encoding="utf-8")
    with pytest.raises(RuntimeError, match="at least 12 bytes"):
        await service.init_admin_password(short_file)

    # 3. Valid password -> bootstrap success
    valid_pass = secrets.token_urlsafe(32)
    valid_file = tmp_path / "admin.pwd"
    valid_file.write_text(valid_pass, encoding="utf-8")
    await service.init_admin_password(valid_file)

    async with session_maker() as session:
        query = select(AdminModel).where(AdminModel.username == "admin")
        admin = (await session.execute(query)).scalar_one()
        assert admin.password_hash.startswith("$argon2id$")
        # Ensure raw password is NOT stored anywhere in DB
        assert valid_pass not in admin.password_hash

    # 4. Existing admin is NOT overwritten, even if password file changes
    other_file = tmp_path / "other.pwd"
    other_file.write_text("another_valid_password_456", encoding="utf-8")
    await service.init_admin_password(other_file)

    # Old password still works, new one is ignored
    ok, _ = await service.authenticate_admin(valid_pass, "127.0.0.1")
    assert ok is True
    ok2, _ = await service.authenticate_admin("another_valid_password_456", "127.0.0.1")
    assert ok2 is False


@pytest.mark.asyncio
async def test_admin_auth_and_rate_limiting(auth_db, tmp_path: Path):
    service, _ = auth_db
    valid_pass = "admin_secure_password_12345"
    valid_file = tmp_path / "admin.pwd"
    valid_file.write_text(valid_pass, encoding="utf-8")
    await service.init_admin_password(valid_file)

    client_ip = "192.168.1.100"

    # 5 consecutive failed attempts
    for _ in range(5):
        ok, reason = await service.authenticate_admin("wrong_password", client_ip)
        assert ok is False
        assert reason == "invalid_credentials"

    # 6th attempt is rate-limited!
    ok, reason = await service.authenticate_admin(valid_pass, client_ip)
    assert ok is False
    assert reason == "rate_limited"

    # Other IP is NOT rate limited
    other_ip = "192.168.1.101"
    ok, _ = await service.authenticate_admin(valid_pass, other_ip)
    assert ok is True


@pytest.mark.asyncio
async def test_session_lifecycle_and_revocation(auth_db):
    service, _ = auth_db

    # Create session
    raw_token, csrf_token, model = await service.create_session(expire_hours=12)
    assert raw_token is not None
    assert csrf_token is not None
    # Token in DB is hashed with SHA-256
    assert raw_token != model.token_hash

    # Validate active session
    valid_session = await service.get_valid_session(raw_token)
    assert valid_session is not None
    assert valid_session.csrf_token == csrf_token

    # Random token is invalid
    assert await service.get_valid_session("invalid_token_xyz") is None

    # Revoke session
    revoked = await service.revoke_session(raw_token)
    assert revoked is True
    assert await service.get_valid_session(raw_token) is None


@pytest.mark.asyncio
async def test_automation_token_lifecycle_and_audit(auth_db):
    service, session_maker = auth_db

    raw_token, model = await service.create_automation_token(
        name="test_worker", profile_ids=["prof-a", "prof-b"]
    )
    assert raw_token.startswith("cbat_")
    token_id = model.id

    # Check audit log for token creation: details NEVER contain token or hash
    async with session_maker() as session:
        audits = (
            (
                await session.execute(
                    select(AuditEventModel).where(AuditEventModel.entity_id == token_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(audits) == 1
        create_audit = audits[0]
        assert create_audit.action == "create"
        assert raw_token not in create_audit.details
        assert model.token_hash not in create_audit.details
        details = json.loads(create_audit.details)
        assert details["name"] == "test_worker"

    # List tokens: plaintext token is NOT returned
    token_list = await service.list_automation_tokens()
    matching = [t for t in token_list if t.id == token_id]
    assert len(matching) == 1
    assert matching[0].name == "test_worker"
    assert not matching[0].revoked

    # Revoke token
    res = await service.revoke_automation_token(token_id)
    assert res is True

    # Audit log for revoke
    async with session_maker() as session:
        revoke_audit = (
            await session.execute(
                select(AuditEventModel)
                .where(AuditEventModel.entity_id == token_id)
                .where(AuditEventModel.action == "revoke")
            )
        ).scalar_one()
        assert revoke_audit.action == "revoke"
        assert raw_token not in revoke_audit.details
        assert model.token_hash not in revoke_audit.details


ALLOWED_ORIGINS = ["https://app.cbrowser.local", "http://localhost:3000"]
PROF_ID = "prof-999"


async def _profile_with_session(service, session_maker) -> str:
    """Seed the shared profile row and return a fresh session token."""
    async with session_maker() as session, write_transaction(session):
        session.add(
            ProfileModel(
                id=PROF_ID,
                name="Test Profile",
                fingerprint_seed=123456,
                user_data_dir="/tmp/test",
            )
        )
    session_token, _, _ = await service.create_session()
    return session_token


@pytest.mark.asyncio
async def test_viewer_authorize_accepts_allowed_origin_and_variants(auth_db):
    service, session_maker = auth_db
    session_token = await _profile_with_session(service, session_maker)

    ok, reason = await service.authorize_viewer(
        session_token, "https://app.cbrowser.local", PROF_ID, ALLOWED_ORIGINS
    )
    assert ok is True
    assert reason is None

    # A42: origin variants of an allowed origin are the same origin after
    # the shared normalization (trailing slash, default port, case).
    for variant in (
        "https://app.cbrowser.local/",
        "https://app.cbrowser.local:443",
        "HTTPS://APP.CBROWSER.LOCAL",
    ):
        ok, reason = await service.authorize_viewer(
            session_token, variant, PROF_ID, ALLOWED_ORIGINS
        )
        assert ok is True, (variant, reason)
        assert reason is None


@pytest.mark.asyncio
async def test_viewer_authorize_rejects_invalid_and_malformed_origins(auth_db):
    service, session_maker = auth_db
    session_token = await _profile_with_session(service, session_maker)

    ok, reason = await service.authorize_viewer(
        session_token, "https://evil.com", PROF_ID, ALLOWED_ORIGINS
    )
    assert ok is False
    assert reason == "invalid_origin"

    # A malformed origin is an invalid origin, not an exception.
    ok, reason = await service.authorize_viewer(
        session_token, "not a url", PROF_ID, ALLOWED_ORIGINS
    )
    assert ok is False
    assert reason == "invalid_origin"


@pytest.mark.asyncio
async def test_viewer_authorize_rejects_invalid_session_and_missing_profile(auth_db):
    service, session_maker = auth_db
    session_token = await _profile_with_session(service, session_maker)

    ok, reason = await service.authorize_viewer(
        "bad_session", "https://app.cbrowser.local", PROF_ID, ALLOWED_ORIGINS
    )
    assert ok is False
    assert reason == "invalid_session"

    ok, reason = await service.authorize_viewer(
        session_token, "https://app.cbrowser.local", "prof-nonexistent", ALLOWED_ORIGINS
    )
    assert ok is False
    assert reason == "profile_not_found"


@pytest.mark.asyncio
async def test_automation_authorize_accepts_scoped_token_rejects_session_cookie(auth_db):
    service, session_maker = auth_db
    session_token = await _profile_with_session(service, session_maker)
    raw_auto_token, _auto_model = await service.create_automation_token(
        name="cdp_bot", profile_ids=[PROF_ID]
    )

    ok, reason = await service.authorize_automation(raw_auto_token, PROF_ID)
    assert ok is True
    assert reason is None

    # Session cookie cannot be used as automation token
    ok, reason = await service.authorize_automation(session_token, PROF_ID)
    assert ok is False
    assert reason == "invalid_token"


@pytest.mark.asyncio
async def test_automation_authorize_unknown_token_audit_aggregates(auth_db):
    service, session_maker = auth_db
    await _profile_with_session(service, session_maker)

    # Policy change (A40): unknown/malformed tokens previously left no
    # audit trace at all. They are now recorded in bounded (reason,
    # source) aggregate rows that count attempts without storing any
    # token material.
    src = "198.51.100.7"
    await service.authorize_automation("not-a-token", PROF_ID, client_ip=src)
    await service.authorize_automation("cbat_unknown", PROF_ID, client_ip=src)
    await service.authorize_automation("cbat_unknown", PROF_ID, client_ip=src)
    async with session_maker() as session:
        aggregates = [
            row
            for row in (
                await session.execute(select(AuditEventModel))
            )
            .scalars()
            .all()
            if row.entity_id == "unknown_token"
            and json.loads(row.details)["source"] == src
        ]
    assert len(aggregates) == 2  # one bucket per denial reason
    by_reason = {json.loads(row.details)["reason"]: row for row in aggregates}
    assert json.loads(by_reason["invalid_token"].details)["count"] == 1
    assert json.loads(by_reason["token_not_found"].details)["count"] == 2
    for row in aggregates:
        assert "cbat_unknown" not in row.details
        assert "not-a-token" not in row.details


@pytest.mark.asyncio
async def test_automation_authorize_expired_token(auth_db):
    service, session_maker = auth_db
    await _profile_with_session(service, session_maker)

    expired_token, _ = await service.create_automation_token(
        name="expired", profile_ids=[PROF_ID], expires_in_hours=-1
    )
    ok, reason = await service.authorize_automation(expired_token, PROF_ID)
    assert ok is False
    assert reason == "token_expired"


@pytest.mark.asyncio
async def test_session_creation_prunes_expired_sessions(auth_db):
    service, session_maker = auth_db
    await _profile_with_session(service, session_maker)

    await service.create_session(expire_hours=0)
    await service.create_session()
    async with session_maker() as session:
        remaining = (await session.execute(select(SessionModel))).scalars().all()
    assert all(row.expires_at > row.created_at for row in remaining)
    assert len(remaining) >= 1


@pytest.mark.asyncio
async def test_automation_authorize_forged_token_throttling(auth_db):
    service, session_maker = auth_db
    await _profile_with_session(service, session_maker)

    # Repeated forged tokens from one source are throttled.
    for _ in range(10):
        await service.authorize_automation(
            "cbat_forged", PROF_ID, client_ip="203.0.113.99"
        )
    ok, reason = await service.authorize_automation(
        "cbat_forged", PROF_ID, client_ip="203.0.113.99"
    )
    assert ok is False
    assert reason == "rate_limited"


@pytest.mark.asyncio
async def test_automation_authorize_unauthorized_profile_revocation_and_audit(auth_db):
    service, session_maker = auth_db
    await _profile_with_session(service, session_maker)
    raw_auto_token, auto_model = await service.create_automation_token(
        name="cdp_bot", profile_ids=[PROF_ID]
    )

    # Unauthorized profile
    ok, reason = await service.authorize_automation(raw_auto_token, "prof-unauthorized")
    assert ok is False
    assert reason == "profile_unauthorized"

    # Revoked token
    await service.revoke_automation_token(auto_model.id)
    ok, reason = await service.authorize_automation(raw_auto_token, PROF_ID)
    assert ok is False
    assert reason == "token_revoked"

    # Check that authorize_denied audit events are recorded without secrets
    async with session_maker() as session:
        denied_query = select(AuditEventModel).where(
            AuditEventModel.action == "authorize_denied"
        )
        denied_audits = (await session.execute(denied_query)).scalars().all()
        assert len(denied_audits) >= 2
        for audit in denied_audits:
            assert raw_auto_token not in audit.details
            assert auto_model.token_hash not in audit.details


def test_missing_auth_service_returns_503():
    from types import SimpleNamespace

    from cbrowser.auth.dependencies import get_auth_service
    from fastapi import HTTPException

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(HTTPException) as exc_info:
        get_auth_service(request)
    assert exc_info.value.status_code == 503


async def _count_loop_ticks(coro, minimum: int):
    """Run *coro* while counting how far a 10ms ticker advances."""
    import asyncio

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    task = asyncio.create_task(ticker())
    try:
        result = await coro
    finally:
        task.cancel()
    assert ticks >= minimum, f"event loop starved: only {ticks} ticks"
    return result


class _SlowHasher:
    """PasswordHasher stand-in whose operations take 300ms of real time."""

    def __init__(self, real, *, slow_verify: bool = True, slow_hash: bool = True):
        import time

        self._real = real
        self._sleep = time.sleep
        self._slow_verify = slow_verify
        self._slow_hash = slow_hash

    def verify(self, hash_: str, password: str) -> bool:
        if self._slow_verify:
            self._sleep(0.3)
        return self._real.verify(hash_, password)

    def hash(self, password: str) -> str:
        if self._slow_hash:
            self._sleep(0.3)
        return self._real.hash(password)


@pytest.mark.asyncio
async def test_argon2_verify_does_not_block_event_loop(auth_db, tmp_path, monkeypatch):
    """AC-003 (A5): real and dummy Argon2 verifies run off the event loop."""
    service, _ = auth_db
    valid_pass = "admin_secure_password_12345"
    valid_file = tmp_path / "admin.pwd"
    valid_file.write_text(valid_pass, encoding="utf-8")
    await service.init_admin_password(valid_file)

    monkeypatch.setattr(
        service, "ph", _SlowHasher(service.ph, slow_hash=False)
    )
    ok, reason = await _count_loop_ticks(
        service.authenticate_admin(valid_pass, "10.1.0.1"), minimum=5
    )
    assert ok is True

    ok, reason = await service.authenticate_admin("wrong_password", "10.1.0.2")
    assert ok is False
    assert reason == "invalid_credentials"


@pytest.mark.asyncio
async def test_argon2_dummy_verify_and_hash_do_not_block_event_loop(
    auth_db, tmp_path, monkeypatch
):
    """AC-003 (A5): the timing-defense dummy verify and bootstrap hash are
    also offloaded; failure behaviour is unchanged when no admin exists."""
    service, _ = auth_db
    monkeypatch.setattr(service, "ph", _SlowHasher(service.ph))
    ok, reason = await _count_loop_ticks(
        service.authenticate_admin("anything", "10.2.0.1"), minimum=5
    )
    assert ok is False
    assert reason == "invalid_credentials"

    valid_file = tmp_path / "admin.pwd"
    valid_file.write_text("admin_secure_password_12345", encoding="utf-8")
    await _count_loop_ticks(service.init_admin_password(valid_file), minimum=5)
    assert await service.has_admin() is True


@pytest.mark.asyncio
async def test_automation_success_does_not_erase_failure_history(
    auth_db,
) -> None:
    """A40: rate-limit failures decay only by the time window.

    Previously record_success wiped the source's failure list, letting a
    valid token holder reset the guessing budget for its source address.
    """
    service, session_maker = auth_db
    prof_id = "prof-999"
    async with session_maker() as session, write_transaction(session):
        session.add(
            ProfileModel(
                id=prof_id,
                name="Test Profile",
                fingerprint_seed=123456,
                user_data_dir="/tmp/test",
            )
        )
    raw, _model = await service.create_automation_token("t", [prof_id])
    source = "203.0.113.55"

    for _ in range(3):
        ok, reason = await service.authorize_automation(
            "cbat_wrong", prof_id, client_ip=source
        )
        assert (ok, reason) == (False, "token_not_found")
    ok, _ = await service.authorize_automation(raw, prof_id, client_ip=source)
    assert ok is True
    # The earlier failures still count after the success: seven more
    # failures reach the per-source budget of ten and throttle the source.
    # Had the success wiped the failure history, this would not throttle.
    for _ in range(7):
        await service.authorize_automation(
            "cbat_wrong", prof_id, client_ip=source
        )
    ok, reason = await service.authorize_automation(
        raw, prof_id, client_ip=source
    )
    assert (ok, reason) == (False, "rate_limited")


@pytest.mark.asyncio
async def test_unknown_token_audit_failure_keeps_clean_denial(
    auth_db, monkeypatch
) -> None:
    """Review f002: the aggregated audit write is best-effort. If it
    fails (e.g. the DB is busy), the caller still gets the clean denial
    reason instead of a propagated storage error, and the failure still
    counts toward the rate limiter."""
    service, session_maker = auth_db

    async def broken_audit(reason: str, source: str) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(
        service, "_record_unknown_token_denied", broken_audit
    )
    ok, reason = await service.authorize_automation(
        "not-a-token", "prof-x", client_ip="198.51.100.23"
    )
    assert (ok, reason) == (False, "invalid_token")
    ok, reason = await service.authorize_automation(
        "cbat_missing", "prof-x", client_ip="198.51.100.24"
    )
    assert (ok, reason) == (False, "token_not_found")
