"""TURN REST HMAC credential generation and verification."""

from __future__ import annotations

import base64
import hashlib
import hmac


def generate_turn_credentials(
    secret: str | bytes,
    profile_id: str,
    role: str,
    expiry_timestamp: int,
) -> tuple[str, str]:
    """Generates TURN REST username and HMAC-SHA1 credential.

    username format: <expiry_unix>:<role>-<profile_id>
    credential format: base64(HMAC-SHA1(secret, username))
    """
    username = f"{expiry_timestamp}:{role}-{profile_id}"
    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    mac = hmac.new(secret_bytes, username.encode("utf-8"), hashlib.sha1).digest()
    credential = base64.b64encode(mac).decode("utf-8")
    return username, credential
