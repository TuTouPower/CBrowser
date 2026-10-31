"""Core authentication and credential management service."""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import secrets
import uuid
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cbrowser.adapters.database.models import (
    AdminModel,
    AuditEventModel,
    AutomationTokenModel,
    ProfileModel,
    SessionModel,
    utc_now_iso,
)
from cbrowser.adapters.database.session import write_transaction
from cbrowser.auth.rate_limiter import LoginRateLimiter
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger("cbrowser.auth")


class AuthService:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        rate_limiter: LoginRateLimiter | None = None,
    ):
        self._session_maker = session_maker
        self.rate_limiter = rate_limiter or LoginRateLimiter(
            max_failures=5, window_seconds=60.0
        )
        self.ph = PasswordHasher()
        self._dummy_hash = self.ph.hash(
            "cbrowser_dummy_password_timing_defense_sentinel"
        )

    async def has_admin(self) -> bool:
        async with self._session_maker() as session:
            admin = (
                (
                    await session.execute(
                        select(AdminModel)
                        .where(AdminModel.username == "admin")
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            return admin is not None

    async def init_admin_password(self, password_file: Path | str | None) -> None:
        """Bootstrap admin credentials from file if no admin exists in database."""
        if await self.has_admin():
            logger.info("Admin account already initialized, skipping password file")
            return

        if password_file is None:
            raise RuntimeError(
                "CBROWSER_ADMIN_PASSWORD_FILE is not configured and no admin exists"
            )

        path = Path(password_file).resolve()
        if not path.is_file():
            raise RuntimeError(f"Admin password file does not exist: {path}")

        try:
            password = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            raise RuntimeError("Cannot read admin password file") from None

        if len(password.encode("utf-8")) < 12:
            raise RuntimeError("Admin password must contain at least 12 bytes")

        password_hash = self.ph.hash(password)
        admin_id = str(uuid.uuid4())

        async with self._session_maker() as session, write_transaction(session):
            session.add(
                AdminModel(
                    id=admin_id,
                    username="admin",
                    password_hash=password_hash,
                )
            )
        logger.info("Admin account successfully bootstrapped")

    async def authenticate_admin(
        self, password: str, client_ip: str
    ) -> tuple[bool, str | None]:
        """Authenticate admin with rate limiting and Argon2 verification."""
        if self.rate_limiter.is_rate_limited(client_ip):
            logger.warning("Admin login rate limited for source")
            return False, "rate_limited"

        async with self._session_maker() as session:
            admin = (
                (
                    await session.execute(
                        select(AdminModel)
                        .where(AdminModel.username == "admin")
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )

            if admin is None:
                # Perform dummy verification to prevent timing attack
                try:
                    self.ph.verify(self._dummy_hash, password)
                except VerificationError:
                    pass
                self.rate_limiter.record_failure(client_ip)
                return False, "invalid_credentials"

            try:
                self.ph.verify(admin.password_hash, password)
                self.rate_limiter.record_success(client_ip)
                return True, None
            except (VerifyMismatchError, VerificationError):
                self.rate_limiter.record_failure(client_ip)
                return False, "invalid_credentials"

    async def create_session(
        self, expire_hours: int = 12
    ) -> tuple[str, str, SessionModel]:
        """Create a new session, returning (session_token, csrf_token, model)."""
        raw_session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_session_token.encode("utf-8")).hexdigest()

        now = datetime.datetime.now(datetime.UTC)
        expires_at = (now + datetime.timedelta(hours=expire_hours)).isoformat()
        session_id = str(uuid.uuid4())

        model = SessionModel(
            id=session_id,
            token_hash=token_hash,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )

        async with self._session_maker() as session, write_transaction(session):
            session.add(model)

        return raw_session_token, csrf_token, model

    async def get_valid_session(self, raw_session_token: str) -> SessionModel | None:
        """Validate session token against database and expiration time."""
        if not raw_session_token:
            return None
        token_hash = hashlib.sha256(raw_session_token.encode("utf-8")).hexdigest()

        async with self._session_maker() as session:
            row = (
                (
                    await session.execute(
                        select(SessionModel).where(
                            SessionModel.token_hash == token_hash
                        )
                    )
                )
                .scalars()
                .first()
            )

            if row is None:
                return None

            try:
                exp = datetime.datetime.fromisoformat(row.expires_at)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=datetime.UTC)
                if datetime.datetime.now(datetime.UTC) >= exp:
                    return None
            except (ValueError, TypeError):
                return None

            return row

    async def revoke_session(self, raw_session_token: str) -> bool:
        """Revoke a session by removing it from the database."""
        if not raw_session_token:
            return False
        token_hash = hashlib.sha256(raw_session_token.encode("utf-8")).hexdigest()

        async with self._session_maker() as session, write_transaction(session):
            res = await session.execute(
                delete(SessionModel).where(SessionModel.token_hash == token_hash)
            )
            return bool(res.rowcount and res.rowcount > 0)

    async def create_automation_token(
        self, name: str, profile_ids: list[str]
    ) -> tuple[str, AutomationTokenModel]:
        """Create an automation token with cbat_ prefix."""
        raw_token = f"cbat_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        token_id = str(uuid.uuid4())
        now = utc_now_iso()

        model = AutomationTokenModel(
            id=token_id,
            name=name,
            token_hash=token_hash,
            profile_ids=json.dumps(profile_ids),
            revoked=False,
            created_at=now,
        )

        audit = AuditEventModel(
            id=str(uuid.uuid4()),
            entity_type="automation_token",
            entity_id=token_id,
            action="create",
            actor="admin",
            details=json.dumps(
                {"token_id": token_id, "name": name, "profile_ids": profile_ids}
            ),
            created_at=now,
        )

        async with self._session_maker() as session, write_transaction(session):
            session.add(model)
            session.add(audit)

        return raw_token, model

    async def list_automation_tokens(self) -> list[AutomationTokenModel]:
        """List all automation tokens without exposing secrets."""
        async with self._session_maker() as session:
            rows = (
                (
                    await session.execute(
                        select(AutomationTokenModel).order_by(
                            AutomationTokenModel.created_at.desc()
                        )
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)

    async def revoke_automation_token(self, token_id: str) -> bool:
        """Revoke an automation token and write audit record."""
        now = utc_now_iso()
        async with self._session_maker() as session, write_transaction(session):
            row = await session.get(AutomationTokenModel, token_id)
            if row is None or row.revoked:
                return False
            row.revoked = True
            row.revoked_at = now
            audit = AuditEventModel(
                id=str(uuid.uuid4()),
                entity_type="automation_token",
                entity_id=token_id,
                action="revoke",
                actor="admin",
                details=json.dumps({"token_id": token_id, "revoked_at": now}),
                created_at=now,
            )
            session.add(audit)
            return True

    async def authorize_viewer(
        self,
        session_token: str,
        origin: str,
        profile_id: str,
        allowed_origins: list[str],
    ) -> tuple[bool, str | None]:
        """Authorize a Viewer connection."""
        sess = await self.get_valid_session(session_token)
        if sess is None:
            return False, "invalid_session"

        if origin not in allowed_origins:
            return False, "invalid_origin"

        async with self._session_maker() as session:
            prof = await session.get(ProfileModel, profile_id)
            if prof is None:
                return False, "profile_not_found"

        return True, None

    async def authorize_automation(
        self, token: str, profile_id: str
    ) -> tuple[bool, str | None]:
        """Authorize an automation client."""
        if not token or not token.startswith("cbat_"):
            await self._record_auth_denied(
                "unknown", profile_id, "invalid_token_format"
            )
            return False, "invalid_token"

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with self._session_maker() as session:
            row = (
                (
                    await session.execute(
                        select(AutomationTokenModel).where(
                            AutomationTokenModel.token_hash == token_hash
                        )
                    )
                )
                .scalars()
                .first()
            )

            if row is None:
                await self._record_auth_denied("unknown", profile_id, "token_not_found")
                return False, "token_not_found"

            if row.revoked:
                await self._record_auth_denied(row.id, profile_id, "token_revoked")
                return False, "token_revoked"

            try:
                allowed_pids = json.loads(row.profile_ids)
            except (json.JSONDecodeError, TypeError):
                allowed_pids = []

            if profile_id not in allowed_pids:
                await self._record_auth_denied(
                    row.id, profile_id, "profile_unauthorized"
                )
                return False, "profile_unauthorized"

            prof = await session.get(ProfileModel, profile_id)
            if prof is None:
                await self._record_auth_denied(row.id, profile_id, "profile_not_found")
                return False, "profile_not_found"

        return True, None

    async def _record_auth_denied(
        self, entity_id: str, profile_id: str, reason: str
    ) -> None:
        now = utc_now_iso()
        async with self._session_maker() as session, write_transaction(session):
            audit = AuditEventModel(
                id=str(uuid.uuid4()),
                entity_type="automation_token",
                entity_id=entity_id,
                action="authorize_denied",
                actor="gateway",
                details=json.dumps({"profile_id": profile_id, "reason": reason}),
                created_at=now,
            )
            session.add(audit)
