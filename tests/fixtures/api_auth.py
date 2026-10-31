"""Shared test fixtures for API user authentication and write protection."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class AuthTestContext:
    admin_password: str
    admin_password_file: Path
    allowed_origin: str
    env: dict[str, str]

    def login_sync(
        self, base_url: str, client: httpx.Client | None = None
    ) -> dict[str, str]:
        """Perform login and return auth headers for write requests."""
        should_close = False
        if client is None:
            client = httpx.Client(base_url=base_url, timeout=10.0, trust_env=False)
            should_close = True

        try:
            resp = client.post(
                "/api/v1/auth/login",
                json={"password": self.admin_password},
            )
            resp.raise_for_status()
            data = resp.json()
            csrf_token = data["csrf_token"]
            session_cookie = resp.cookies.get("cbrowser_session")
            if not session_cookie:
                # Fallback to parsing Set-Cookie header manually
                for val in resp.headers.get_list("set-cookie"):
                    if "cbrowser_session=" in val:
                        part = val.split("cbrowser_session=", 1)[1]
                        session_cookie = part.split(";", 1)[0]
                        break

            return {
                "Cookie": f"cbrowser_session={session_cookie}",
                "X-CSRF-Token": csrf_token,
                "Origin": self.allowed_origin,
            }
        finally:
            if should_close:
                client.close()

    async def login_async(
        self, base_url: str, client: httpx.AsyncClient | None = None
    ) -> dict[str, str]:
        """Async perform login and return auth headers for write requests."""
        should_close = False
        if client is None:
            client = httpx.AsyncClient(base_url=base_url, timeout=10.0, trust_env=False)
            should_close = True

        try:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"password": self.admin_password},
            )
            resp.raise_for_status()
            data = resp.json()
            csrf_token = data["csrf_token"]
            session_cookie = resp.cookies.get("cbrowser_session")
            if not session_cookie:
                for val in resp.headers.get_list("set-cookie"):
                    if "cbrowser_session=" in val:
                        part = val.split("cbrowser_session=", 1)[1]
                        session_cookie = part.split(";", 1)[0]
                        break

            return {
                "Cookie": f"cbrowser_session={session_cookie}",
                "X-CSRF-Token": csrf_token,
                "Origin": self.allowed_origin,
            }
        finally:
            if should_close:
                await client.aclose()


def create_auth_context(
    dir_path: Path,
    origin: str = "http://127.0.0.1",
) -> AuthTestContext:
    """Create a randomized admin password file (0600) and return AuthTestContext."""
    dir_path.mkdir(parents=True, exist_ok=True)
    admin_password = secrets.token_urlsafe(32)
    pwd_file = dir_path / f"admin_pwd_{secrets.token_hex(6)}.txt"
    pwd_file.write_text(admin_password, encoding="utf-8")
    pwd_file.chmod(0o600)

    env = {
        "CBROWSER_ADMIN_PASSWORD_FILE": str(pwd_file),
        "CBROWSER_ALLOWED_ORIGINS": origin,
    }

    return AuthTestContext(
        admin_password=admin_password,
        admin_password_file=pwd_file,
        allowed_origin=origin,
        env=env,
    )
