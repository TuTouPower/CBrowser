"""Unit tests for auth database models on the t035 baseline schema.

t035 (AC-001/AC-002): the 0001-0009 chain was collapsed into a single
baseline revision.  The old "migration 0002_auth" naming is removed; no
assertion here hardcoded a retired revision id, so these tests are kept
verbatim (they exercise ORM writes against an empty DB upgraded to head).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.models import (
    AdminModel,
    AutomationTokenModel,
    SessionModel,
)
from cbrowser.adapters.database.session import (
    create_engine_and_maker,
    write_transaction,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_baseline_creates_auth_tables(tmp_path: Path):
    db_file = tmp_path / "auth_migration_test.db"
    run_database_migrations(db_file)

    engine, session_maker = create_engine_and_maker(db_file)
    try:
        async with session_maker() as session, write_transaction(session):
            admin = AdminModel(
                id=str(uuid.uuid4()),
                username="admin",
                password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
            )
            session.add(admin)

            session_obj = SessionModel(
                id=str(uuid.uuid4()),
                token_hash="hash_session_123",
                csrf_token="csrf_token_123",
                expires_at="2026-10-31T00:00:00+00:00",
            )
            session.add(session_obj)

            auto_token = AutomationTokenModel(
                id=str(uuid.uuid4()),
                name="ci_token",
                token_hash="hash_token_123",
                profile_ids='["prof-1", "prof-2"]',
            )
            session.add(auto_token)

        async with session_maker() as session:
            admin_db = (
                await session.execute(
                    select(AdminModel).where(AdminModel.username == "admin")
                )
            ).scalar_one()
            assert admin_db.username == "admin"
            assert "dummyhash" in admin_db.password_hash

            session_db = (
                await session.execute(
                    select(SessionModel).where(
                        SessionModel.token_hash == "hash_session_123"
                    )
                )
            ).scalar_one()
            assert session_db.csrf_token == "csrf_token_123"

            token_db = (
                await session.execute(
                    select(AutomationTokenModel).where(
                        AutomationTokenModel.token_hash == "hash_token_123"
                    )
                )
            ).scalar_one()
            assert token_db.name == "ci_token"
            assert not token_db.revoked

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_auth_models_unique_constraints(tmp_path: Path):
    db_file = tmp_path / "auth_unique_test.db"
    run_database_migrations(db_file)

    engine, session_maker = create_engine_and_maker(db_file)
    try:
        # Test unique username on admins
        async with session_maker() as session, write_transaction(session):
            session.add(
                AdminModel(
                    id="admin-1",
                    username="admin",
                    password_hash="hash1",
                )
            )

        with pytest.raises(IntegrityError):
            async with session_maker() as session, write_transaction(session):
                session.add(
                    AdminModel(
                        id="admin-2",
                        username="admin",
                        password_hash="hash2",
                    )
                )

        # Test unique token_hash on sessions
        async with session_maker() as session, write_transaction(session):
            session.add(
                SessionModel(
                    id="s-1",
                    token_hash="same_session_hash",
                    csrf_token="c1",
                    expires_at="2026-10-31T00:00:00+00:00",
                )
            )

        with pytest.raises(IntegrityError):
            async with session_maker() as session, write_transaction(session):
                session.add(
                    SessionModel(
                        id="s-2",
                        token_hash="same_session_hash",
                        csrf_token="c2",
                        expires_at="2026-10-31T00:00:00+00:00",
                    )
                )

        # Test unique token_hash on automation_tokens
        async with session_maker() as session, write_transaction(session):
            session.add(
                AutomationTokenModel(
                    id="t-1",
                    name="token-1",
                    token_hash="same_auto_hash",
                    profile_ids="[]",
                )
            )

        with pytest.raises(IntegrityError):
            async with session_maker() as session, write_transaction(session):
                session.add(
                    AutomationTokenModel(
                        id="t-2",
                        name="token-2",
                        token_hash="same_auto_hash",
                        profile_ids="[]",
                    )
                )

    finally:
        await engine.dispose()
