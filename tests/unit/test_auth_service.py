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


@pytest.mark.asyncio
async def test_viewer_and_automation_authorize(auth_db):
    service, session_maker = auth_db

    # Create dummy profile in DB
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

    # 1. Viewer authorization
    session_token, _, _ = await service.create_session()
    allowed_origins = ["https://app.cbrowser.local", "http://localhost:3000"]

    ok, reason = await service.authorize_viewer(
        session_token, "https://app.cbrowser.local", prof_id, allowed_origins
    )
    assert ok is True
    assert reason is None

    # Invalid origin
    ok, reason = await service.authorize_viewer(
        session_token, "https://evil.com", prof_id, allowed_origins
    )
    assert ok is False
    assert reason == "invalid_origin"

    # Invalid session
    ok, reason = await service.authorize_viewer(
        "bad_session", "https://app.cbrowser.local", prof_id, allowed_origins
    )
    assert ok is False
    assert reason == "invalid_session"

    # Nonexistent profile
    ok, reason = await service.authorize_viewer(
        session_token, "https://app.cbrowser.local", "prof-nonexistent", allowed_origins
    )
    assert ok is False
    assert reason == "profile_not_found"

    # 2. Automation authorization
    raw_auto_token, auto_model = await service.create_automation_token(
        name="cdp_bot", profile_ids=[prof_id]
    )

    # Valid automation token for prof_id
    ok, reason = await service.authorize_automation(raw_auto_token, prof_id)
    assert ok is True
    assert reason is None

    # Session cookie cannot be used as automation token
    ok, reason = await service.authorize_automation(session_token, prof_id)
    assert ok is False
    assert reason == "invalid_token"

    # Unauthorized profile
    ok, reason = await service.authorize_automation(raw_auto_token, "prof-unauthorized")
    assert ok is False
    assert reason == "profile_unauthorized"

    # Revoked token
    await service.revoke_automation_token(auto_model.id)
    ok, reason = await service.authorize_automation(raw_auto_token, prof_id)
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
